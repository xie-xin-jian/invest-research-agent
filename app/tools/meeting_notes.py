"""会议纪要结构化：把口语化的会议纪要整理成结构化卡片。"""
from __future__ import annotations

from typing import Iterator

from app.llm import chat, chat_stream

_SYSTEM = "你是会议秘书，擅长把零散的口语化纪要整理成结构化、可跟进的会议记录。"

_TEMPLATE = """请阅读以下会议纪要原文，整理成结构化输出。

==== 纪要原文开始 ====
{content}
==== 纪要原文结束 ====

输出 Markdown，包含以下固定小节：

## 会议主题
- 一句话

## 议题与决议
- 用表格：议题 | 讨论 | 最终决议

## 行动项
- 用表格：负责人 | 待办事项 | 截止时间
- 没有明确负责人的标"待定"，没有明确时间标"待定"

## 待跟进
- 3 条下次会议需要 revisit 的开放问题

注意：不要补造原文中没有的决议或行动项；原文信息不足时直接说明。"""


def structure(content: str) -> str:
    """把会议纪要原文整理成结构化 Markdown。"""
    if len(content.strip()) < 50:
        return "会议纪要原文不足 50 字，请粘贴更完整的纪要文本。"
    return chat(_TEMPLATE.format(content=content[:12000]), system=_SYSTEM, max_tokens=2048)


def structure_stream(content: str) -> Iterator[str]:
    """流式整理会议纪要，逐 token 返回。原文过短时直接返回提示。"""
    if len(content.strip()) < 50:
        yield "会议纪要原文不足 50 字，请粘贴更完整的纪要文本。"
        return
    yield from chat_stream(_TEMPLATE.format(content=content[:12000]), system=_SYSTEM, max_tokens=2048)
