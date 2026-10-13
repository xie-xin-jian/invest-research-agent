"""联网搜索工具：基于 DuckDuckGo（免费、无需 API key）。

JD 里"自动搜集和整理行业信息"靠它落地：模型判断需要最新信息时自己调用。
"""
from __future__ import annotations


def search(query: str, max_results: int = 6) -> str:
    """搜索互联网，返回若干条结果（标题/链接/摘要）拼成的文本。"""
    from ddgs import DDGS

    try:
        with DDGS() as ddgs:
            results = list(ddgs.text(query, max_results=max_results))
    except Exception as e:
        return f"Error: 搜索失败: {e}"

    if not results:
        return f"未搜索到与「{query}」相关的结果，可以换个关键词再试。"

    lines = []
    for i, r in enumerate(results, 1):
        title = r.get("title", "").strip()
        href = r.get("href", "").strip()
        body = r.get("body", "").strip()
        lines.append(f"{i}. {title}\n   链接: {href}\n   摘要: {body}")
    return "\n\n".join(lines)
