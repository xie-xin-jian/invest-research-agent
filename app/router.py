"""消息路由：根据用户一句话判断走哪个工具，并组装结果。"""
from __future__ import annotations

from typing import Iterator

from app.llm import chat_stream
from app.tools import industry_research, meeting_notes, report_reader

_GENERAL_SYSTEM = """你是「投研助理」机器人，在飞书里服务投资研究团队。
用户闲聊或自由提问时，用简洁、专业、友好的方式自然回答（200 字以内），不要硬套模板。
你还有三个固定功能，如果用户的需求正好匹配，用一句话提示用法：
- 研究下XX行业 → 生成结构化行业简报
- 读研报：[粘贴文本]，或直接发文件 → 研报速读摘要
- 纪要：[粘贴文本] → 会议纪要结构化"""


def route(user_text: str) -> str:
    """非流式版本：收集全部输出后一次性返回。"""
    return "".join(route_stream(user_text))


def route_stream(user_text: str) -> Iterator[str]:
    """根据用户输入的关键词路由到对应工具，逐 token 返回结果。

    规则（按优先级）：
    1. 命中"纪要 / 会议 / 复盘" → meeting_notes
    2. 命中"读研报 / 研报 / 速读 / 摘要" → report_reader
    3. 命中"研究 / 调研 / 行业 / 赛道" → industry_research（固定简报模板）
    4. 兜底：通用投研问答（自由回答，不套模板）
    """
    text = user_text.strip()

    if any(k in text for k in ("纪要", "会议", "复盘", "整理一下", "整理这段")):
        # 纪要场景：用户大概率会粘贴纪要原文
        # 这里取换行后的内容作为正文，前缀作为指令
        content = _strip_prefix(text, ("纪要", "会议", "复盘", "整理一下", "整理这段"))
        yield from meeting_notes.structure_stream(content)
        return

    if any(k in text for k in ("读研报", "研报", "速读", "摘要", "读一下", "读这份")):
        content = _strip_prefix(text, ("读研报", "研报", "速读", "摘要", "读一下", "读这份"))
        yield from report_reader.read_stream(content)
        return

    if any(k in text for k in ("研究", "调研", "行业", "赛道")):
        topic = _strip_prefix(text, ("研究", "调研", "看一下", "查一下", "帮我看"))
        yield from industry_research.research_stream(topic or text)
        return

    # 兜底：通用投研问答
    yield from chat_stream(text, system=_GENERAL_SYSTEM, max_tokens=1024)


def _strip_prefix(text: str, prefixes: tuple[str, ...]) -> str:
    """去掉指令前缀，保留正文（用于粘贴场景）。"""
    out = text
    for p in prefixes:
        if out.startswith(p):
            out = out[len(p):]
    return out.strip("：: ，,。.\n ")
