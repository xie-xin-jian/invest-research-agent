"""投研工具注册：把 app.tools 里的函数包装成 (schema, handler) 注册进 Agent。

schema 的 description 是给模型看的"使用说明"，写得越清楚，模型选工具越准。
"""
from __future__ import annotations

from app.tools import industry_research, meeting_notes, report_reader, web_search


def register_research_tools(registry) -> None:
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
