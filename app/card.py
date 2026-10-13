"""把 Markdown 转成飞书交互卡片结构。

飞书卡片支持 markdown 元素，但卡片 JSON 有固定结构。
这里做一个最简实现：把 Markdown 包装进一个 markdown 卡片块。
"""
from __future__ import annotations


def markdown_to_card(md: str, title: str = "投研助理") -> dict:
    """把 Markdown 文本包装成飞书交互卡片 JSON。

    文档：https://open.feishu.cn/document/uAjLw4CM/ukTMukTMukTM/feishu-cards/card-json-structure
    """
    return {
        "config": {"wide_screen_mode": True},
        "header": {
            "title": {"tag": "plain_text", "content": title},
            "template": "green",
        },
        "elements": [
            {"tag": "markdown", "content": md},
            {"tag": "hr"},
            {
                "tag": "note",
                "elements": [
                    {
                        "tag": "plain_text",
                        "content": "由 DeepSeek 驱动 · 飞书一句话投研 Bot",
                    }
                ],
            },
        ],
    }
