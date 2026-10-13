"""投研工具注册：把 app.tools 里的函数包装成 (schema, handler) 注册进 Agent。

schema 的 description 是给模型看的"使用说明"，写得越清楚，模型选工具越准。
"""
from __future__ import annotations

from app.tools import industry_research, meeting_notes, report_reader, web_search


def register_research_tools(registry, chat_id: str = "") -> None:
    registry.register(
        {
            "name": "web_search",
            "description": (
                "联网搜索最新行业信息、公司动态、融资新闻等。"
                "当问题涉及最新/近期/当前信息，或对事实不确定时使用。"
                "返回若干条搜索结果的标题、链接和摘要。"
            ),
            "input_schema": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "搜索关键词，中英文均可，建议具体一些（如'人形机器人 2025 融资'）",
                    },
                },
                "required": ["query"],
            },
        },
        web_search.search,
    )

    registry.register(
        {
            "name": "industry_research",
            "description": (
                "针对一个行业/赛道生成结构化投研简报，固定小节："
                "行业概览、头部玩家、关键数据、驱动因素与风险、建议关注。"
                "适合用户想快速了解一个行业全貌时使用。"
            ),
            "input_schema": {
                "type": "object",
                "properties": {
                    "topic": {
                        "type": "string",
                        "description": "行业或主题名称，如'人形机器人'、'低空经济'",
                    },
                },
                "required": ["topic"],
            },
        },
        industry_research.research,
    )

    registry.register(
        {
            "name": "report_reader",
            "description": (
                "速读研报/招股书/公告等长文本，输出结构化摘要："
                "核心结论、关键数据表格、风险提示、适合谁看。"
                "当用户粘贴了大段研报类材料时使用。"
            ),
            "input_schema": {
                "type": "object",
                "properties": {
                    "content": {
                        "type": "string",
                        "description": "研报正文纯文本（不足 200 字会提示信息量不够）",
                    },
                },
                "required": ["content"],
            },
        },
        report_reader.read,
    )

    registry.register(
        {
            "name": "meeting_notes",
            "description": (
                "把会议纪要原文结构化为：会议主题、议题与决议表格、行动项表格、待跟进问题。"
                "当用户粘贴了会议记录/讨论内容时使用。"
            ),
            "input_schema": {
                "type": "object",
                "properties": {
                    "content": {
                        "type": "string",
                        "description": "会议纪要原文纯文本（不足 50 字会提示补充）",
                    },
                },
                "required": ["content"],
            },
        },
        meeting_notes.structure,
    )

    # 日报管理工具：用户在飞书对话里直接管理定时日报（无需 curl）
    if chat_id:
        from app.agent import daily_report

        def _manage_report(action: str, topic: str = "", cron: str = "", job_id: str = "") -> str:
            """日报任务的创建/查看/删除/立即触发。chat_id 从飞书消息上下文自动获取，模型无需提供。"""
            if action == "create":
                if not topic or not cron:
                    return "Error: 创建日报需要提供 topic（主题）和 cron（定时表达式，如 0 9 * * *）"
                try:
                    job = daily_report.add_job(cron=cron, chat_id=chat_id, topic=topic)
                except ValueError as e:
                    return f"Error: {e}"
                return (
                    f"✅ 已创建日报任务\n"
                    f"- 主题：{topic}\n"
                    f"- 定时：{cron}（时区 Asia/Shanghai）\n"
                    f"- 推送到当前群\n"
                    f"- 任务ID：{job.id}\n"
                    f"到时间会自动搜索最新动态并整理成日报卡片推到这个群。"
                )
            elif action == "list":
                jobs = daily_report.list_jobs()
                if not jobs:
                    return "当前没有任何日报任务。"
                lines = [f"共 {len(jobs)} 个日报任务："]
                for j in jobs:
                    status = "启用" if j.get("enabled", True) else "停用"
                    lines.append(f"- [{status}] {j['topic']} | cron: {j['cron']} | ID: {j['id']}")
                return "\n".join(lines)
            elif action == "delete":
                if not job_id and not topic:
                    return "Error: 删除日报需要提供 job_id 或 topic"
                if not job_id and topic:
                    for j in daily_report.list_jobs():
                        if j.get("topic") == topic:
                            job_id = j["id"]
                            break
                if not job_id:
                    return f"Error: 没找到主题为「{topic}」的日报任务"
                ok = daily_report.remove_job(job_id)
                return f"✅ 已删除日报任务（ID: {job_id}）" if ok else "Error: 删除失败，任务不存在"
            elif action == "run":
                if not job_id and not topic:
                    return "Error: 立即触发需要提供 job_id 或 topic"
                if not job_id and topic:
                    for j in daily_report.list_jobs():
                        if j.get("topic") == topic:
                            job_id = j["id"]
                            break
                if not job_id:
                    return f"Error: 没找到主题为「{topic}」的日报任务"
                import threading
                jobs = {j["id"]: j for j in daily_report.list_jobs()}
                jd = jobs.get(job_id)
                if not jd:
                    return f"Error: 任务 {job_id} 不存在"
                job = daily_report.ReportJob(**jd)
                threading.Thread(target=daily_report.run_job, args=(job,), daemon=True).start()
                return f"⏳ 已触发「{job.topic}」日报，正在搜索整理，稍后推送到群里。"
            else:
                return f"Error: 未知操作 '{action}'，支持：create / list / delete / run"

        registry.register(
            {
                "name": "manage_report",
                "description": (
                    "管理每日行业日报定时任务。用户可以在对话里直接订阅/查看/取消/立即推送日报，无需命令行。"
                    "支持的操作：\n"
                    "- create：订阅日报（需要 topic 和 cron）\n"
                    "- list：查看所有日报任务\n"
                    "- delete：取消日报（需要 topic 或 job_id）\n"
                    "- run：立即推送一次日报（需要 topic 或 job_id）\n"
                    "当用户说'订阅日报'、'每天推送'、'取消日报'、'现在推一次'时使用此工具。"
                ),
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "action": {
                            "type": "string",
                            "enum": ["create", "list", "delete", "run"],
                            "description": "操作类型",
                        },
                        "topic": {
                            "type": "string",
                            "description": "日报主题，如'人形机器人'、'固态电池'。create/delete/run 时需要",
                        },
                        "cron": {
                            "type": "string",
                            "description": "5段cron表达式，如'0 9 * * *'（每天9点）、'0 9 * * 1-5'（工作日9点）。仅 create 需要",
                        },
                        "job_id": {
                            "type": "string",
                            "description": "任务ID（list 返回的 rpt_xxx）。delete/run 时可用 job_id 或 topic 指定",
                        },
                    },
                    "required": ["action"],
                },
            },
            _manage_report,
        )

    # 文档导出工具：把内容转成 Word 发到群里
    if chat_id:
        from app import feishu_client, docx_export
        from app.card import markdown_to_card

        def _export_doc(content: str, title: str = "") -> str:
            """把 Markdown 内容转成 Word 文档，上传并发到当前群。"""
            if not content.strip():
                return "Error: content 不能为空"
            doc_title = (title or content[:30] or "投研资料").strip()
            try:
                docx_bytes = docx_export.markdown_to_docx(content, title=doc_title)
                file_key = feishu_client.upload_file(docx_bytes, f"{doc_title[:30]}.docx")
                feishu_client.send_card(
                    chat_id,
                    markdown_to_card(f"✅ 文档已生成：**{doc_title}**（见上方文件）", title="投研助理"),
                )
                # 同时发文件到群
                feishu_client.send_file(chat_id, file_key)
                return f"✅ 文档「{doc_title}」已生成并发到群里。"
            except Exception as e:
                return f"Error: 文档生成失败：{e}"

        registry.register(
            {
                "name": "export_doc",
                "description": (
                    "把 Markdown 内容导出为 Word 文档并发到群里。"
                    "当用户说'转成文档'、'给我文档'、'导出'、'生成文档'时使用。"
                    "content 参数传入要转换的 Markdown 文本（可以是之前生成的日报、简报等）。"
                ),
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "content": {
                            "type": "string",
                            "description": "要转成文档的 Markdown 文本",
                        },
                        "title": {
                            "type": "string",
                            "description": "文档标题（可选，默认取内容前30字）",
                        },
                    },
                    "required": ["content"],
                },
            },
            _export_doc,
        )
