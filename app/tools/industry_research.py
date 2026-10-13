"""行业研究工具：输入一句话行业关键词，输出结构化行业简报。"""
from __future__ import annotations

from typing import Iterator

from app.llm import chat, chat_stream

_SYSTEM = "你是资深行业分析师，擅长用结构化、可执行的方式输出行业简报。输出必须严格遵循 Markdown 的小节结构。"

_TEMPLATE = """请针对以下行业写一份投研简报。

行业 / 主题：{topic}

要求：输出 Markdown，包含以下固定小节，每节 3-6 个要点：

## 一、行业概览
- 一句话定义 + 当前发展阶段（萌芽 / 成长 / 成熟 / 衰退）

## 二、头部玩家
- 用表格列出 3-5 家代表公司：公司 | 主要产品 | 差异化点

## 三、关键数据
- 市场规模、增速、渗透率等 3-5 个有信息量的数字（标注来源年份）

## 四、驱动因素与风险
- 驱动 2-3 条；风险 2-3 条

## 五、建议关注
- 给投研人员 3 条可执行的下一步动作（看哪类公司、跟踪哪些指标）

注意：数据不确定时标"约"，不要编造精确数字。"""


def research(topic: str) -> str:
    """生成一份行业简报 Markdown。"""
    return chat(_TEMPLATE.format(topic=topic), system=_SYSTEM, max_tokens=2048)


def research_stream(topic: str) -> Iterator[str]:
    """流式生成行业简报，逐 token 返回。"""
    return chat_stream(_TEMPLATE.format(topic=topic), system=_SYSTEM, max_tokens=2048)
