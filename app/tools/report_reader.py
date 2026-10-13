"""研报速读：输入长文本（研报 / 招股书 / 公告），输出结构化摘要。"""
from __future__ import annotations

from typing import Iterator

from app.llm import chat, chat_stream

_SYSTEM = "你是资深券商研究员，擅长把长文本压缩成可执行的结构化摘要。"

_TEMPLATE = """请阅读以下文本并生成一份研报速读摘要。

==== 原文开始 ====
{content}
==== 原文结束 ====

输出 Markdown，包含以下固定小节：

## 核心结论
- 3 条最关键的判断（一句话）

## 关键数据
- 5 条最重要的数字 / 指标，用表格：指标 | 数值 | 含义

## 风险提示
- 3 条

## 适合谁看
- 一句话：哪类投资人 / 投研同事应该读这份

注意：原文不足 200 字时直接说明信息不够；不要编造未出现的数字。"""


def read(content: str) -> str:
    """生成研报速读 Markdown。

    content: 已提取好的纯文本（外部调用方负责从附件 / 粘贴文本里提取）。
    """
    if len(content.strip()) < 200:
        return "原文内容不足 200 字，信息量不够生成结构化摘要，请补充更完整的研报文本。"
    return chat(_TEMPLATE.format(content=content[:16000]), system=_SYSTEM, max_tokens=2048)


def read_stream(content: str) -> Iterator[str]:
    """流式生成研报速读，逐 token 返回。原文过短时直接返回提示。"""
    if len(content.strip()) < 200:
        yield "原文内容不足 200 字，信息量不够生成结构化摘要，请补充更完整的研报文本。"
        return
    yield from chat_stream(_TEMPLATE.format(content=content[:16000]), system=_SYSTEM, max_tokens=2048)
