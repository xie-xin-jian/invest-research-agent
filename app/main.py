"""FastAPI 入口：接收飞书事件订阅 webhook。

启动：
    uvicorn app.main:app --host 0.0.0.0 --port 8000
"""
from __future__ import annotations

import json
import logging
import time
from typing import Any, Iterator

from fastapi import BackgroundTasks, FastAPI, Request
from fastapi.responses import JSONResponse

from app import docx_export, feishu_client
from app.card import markdown_to_card
from app.router import _strip_prefix, route_stream
from app.tools import industry_research, report_reader
from config import config

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("feishu-bot")

app = FastAPI(title="Feishu Research Bot")

# 事件去重：记录最近处理过的 event_id（飞书重试会带相同 event_id）
_processed_events: dict[str, float] = {}
_EVENT_TTL = 300.0  # 5 分钟内相同 event_id 视为重复

# 出文档指令关键词：命中后生成资料 → 转 Word → 发回群聊
_DOC_PREFIXES = ("出文档", "生成文档", "整理资料", "写成文档", "导出文档", "给我文档")


def _is_duplicate(event_id: str) -> bool:
    if not event_id:
        return False
    now = time.time()
    # 顺手清理过期记录
    for k in [k for k, t in _processed_events.items() if now - t > _EVENT_TTL]:
        del _processed_events[k]
    if event_id in _processed_events:
        return True
    _processed_events[event_id] = now
    return False


@app.post("/feishu/webhook")
async def webhook(req: Request, background_tasks: BackgroundTasks) -> Any:
    body = await req.json()
    logger.info("recv event: %s", body)

    # 1. URL 验证 challenge（首次配置事件订阅时飞书会发）
    if body.get("type") == "url_verification":
        return JSONResponse({"challenge": body.get("challenge", "")})

    # 2. 校验 verification token
    header = body.get("header", {})
    if header.get("token") and header["token"] != config.feishu.verification_token:
        return JSONResponse({"error": "invalid token"}, status_code=401)

    # 3. 事件去重（双保险：即使飞书重试也只处理一次）
    if _is_duplicate(header.get("event_id", "")):
        logger.info("duplicate event %s, skip", header.get("event_id"))
        return JSONResponse({"ok": True})

    # 4. 解析消息事件
    event = body.get("event", {})
    msg = event.get("message", {})
    if not msg:
        return JSONResponse({"ok": True})

    message_id = msg.get("message_id", "")
    content_str = msg.get("content", "{}")
    chat_type = msg.get("chat_type", "")  # p2p / group

    # 提取用户文本
    user_text = _extract_text(content_str)

    # 群聊场景：只响应@了本机器人的消息（后台若开了"接收所有群消息"，不过滤会白白烧 token）
    if chat_type == "group":
        mentions = msg.get("mentions", [])
        try:
            bot_id = feishu_client.get_bot_open_id()
        except Exception:
            bot_id = ""
        if bot_id:
            if not any(m.get("id", {}).get("open_id") == bot_id for m in mentions):
                logger.info("group msg without @me, skip")
                return JSONResponse({"ok": True})
        elif not mentions:
            return JSONResponse({"ok": True})
        for m in mentions:
            name = m.get("name", "")
            if user_text.startswith(f"@{name}"):
                user_text = user_text[len(f"@{name}"):].strip()
            # 也兼容无空格的 @name 前缀
            if user_text.startswith(name):
                user_text = user_text[len(name):].strip()

    user_text = user_text.strip()

    # 5. 文件消息：下载 → 提取文本 → 速读（飞书事件里字段名是 message_type）
    msg_type = msg.get("message_type", "")
    if msg_type == "file":
        try:
            finfo = json.loads(content_str)
        except Exception:
            finfo = {}
        background_tasks.add_task(
            handle_file_message,
            message_id,
            finfo.get("file_key", ""),
            finfo.get("file_name", "未知文件"),
        )
        return JSONResponse({"ok": True})

    # 6. 文档指令：优先进后台（生成资料 → Word → 发回）
    if user_text and any(k in user_text for k in _DOC_PREFIXES):
        background_tasks.add_task(handle_doc_request, message_id, user_text)
        return JSONResponse({"ok": True})

    # 7. 立即返回 200，耗时处理放后台。
    #    飞书要求 webhook 3 秒内响应，否则重试推送 → 同一消息被处理多次
    background_tasks.add_task(handle_message, message_id, user_text)
    return JSONResponse({"ok": True})


def handle_doc_request(message_id: str, text: str) -> None:
    """后台处理"出文档"指令：行业研究生成资料 → 转 Word → 上传发回群聊。"""
    try:
        placeholder = feishu_client.reply_card(
            message_id,
            markdown_to_card("⏳ 正在生成资料文档，约需 10-20 秒…", title="投研助理"),
        )
        reply_msg_id = placeholder.get("data", {}).get("message_id", message_id)

        topic = _strip_prefix(text, _DOC_PREFIXES) or text
        md = industry_research.research(topic)
        docx_bytes = docx_export.markdown_to_docx(md, title=topic[:30])
        file_key = feishu_client.upload_file(docx_bytes, f"{topic[:30] or '投研资料'}.docx")
        feishu_client.reply_file(message_id, file_key)
        feishu_client.update_card(
            reply_msg_id,
            markdown_to_card(f"✅ 文档已生成：**{topic}**（见上方文件）", title="投研助理"),
        )
    except Exception as e:
        logger.exception("handle doc request failed")
        feishu_client.reply_text(message_id, f"文档生成失败：{e}")


def handle_message(message_id: str, user_text: str) -> None:
    """后台处理消息：占位卡片 → 流式生成 → 节流更新。同步函数，由 BackgroundTasks 跑在线程池。"""
    if not user_text:
        feishu_client.reply_text(message_id, "在的，说一句话试试，比如：\n研究下人形机器人行业\n读研报：[粘贴文本]\n纪要：[粘贴文本]")
        return

    # 先回一条占位卡片，告诉用户在处理
    placeholder = feishu_client.reply_card(
        message_id,
        markdown_to_card("⏳ 正在生成…", title="投研助理"),
    )
    reply_msg_id = placeholder.get("data", {}).get("message_id", message_id)

    try:
        _stream_into_card(reply_msg_id, route_stream(user_text))
    except Exception as e:
        logger.exception("handle failed")
        feishu_client.reply_text(message_id, f"处理失败：{e}")


def handle_file_message(message_id: str, file_key: str, file_name: str) -> None:
    """后台处理文件消息：下载附件 → 提取文本 → 走研报速读流式输出。"""
    try:
        # 先回占位卡片（下载解析可能要几秒）
        placeholder = feishu_client.reply_card(
            message_id,
            markdown_to_card(f"⏳ 正在下载并解析文件：{file_name}…", title="投研助理"),
        )
        reply_msg_id = placeholder.get("data", {}).get("message_id", message_id)

        data = feishu_client.download_file(message_id, file_key)
        text = _extract_file_text(file_name, data)

        if not text.strip():
            feishu_client.update_card(
                reply_msg_id,
                markdown_to_card(
                    f"没从 **{file_name}** 里提取到文字。目前支持 PDF / Word(.docx) / TXT / MD；"
                    "扫描件 PDF（纯图片）需要 OCR，暂不支持。",
                    title="投研助理",
                ),
            )
            return

        logger.info("file %s extracted %d chars, start reading", file_name, len(text))
        _stream_into_card(reply_msg_id, report_reader.read_stream(text))
    except Exception as e:
        logger.exception("handle file failed")
        feishu_client.reply_text(message_id, f"文件处理失败：{e}")


def _stream_into_card(reply_msg_id: str, stream: Iterator[str]) -> None:
    """把流式生成的内容写进一张已存在的卡片：每 1 秒节流更新一次，完成后去掉光标。"""
    buffer = ""
    last_update = 0.0
    for chunk in stream:
        buffer += chunk
        now = time.time()
        if now - last_update >= 1.0:
            feishu_client.update_card(
                reply_msg_id,
                markdown_to_card(buffer + " ▍", title="投研助理"),
            )
            last_update = now
    # 最终完整更新
    feishu_client.update_card(reply_msg_id, markdown_to_card(buffer, title="投研助理"))


def _extract_file_text(file_name: str, data: bytes) -> str:
    """按扩展名从文件字节里提取纯文本。支持 pdf / docx / txt / md。"""
    import io

    name = file_name.lower()
    if name.endswith(".pdf"):
        from pypdf import PdfReader

        reader = PdfReader(io.BytesIO(data))
        return "\n".join(page.extract_text() or "" for page in reader.pages)
    if name.endswith(".docx"):
        import docx

        d = docx.Document(io.BytesIO(data))
        return "\n".join(p.text for p in d.paragraphs if p.text.strip())
    if name.endswith((".txt", ".md")):
        return data.decode("utf-8", errors="ignore")
    return ""


def _extract_text(content_str: str) -> str:
    """从飞书消息 content JSON 里提取文本。支持 text 消息。"""
    import json

    try:
        data = json.loads(content_str)
    except Exception:
        return ""
    # text 消息格式：{"text":"@_user_1 xxx"}
    return data.get("text", "")


@app.get("/")
async def health() -> dict:
    return {"status": "ok", "bot": "feishu-research-bot"}
