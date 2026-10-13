"""DeepSeek 大模型调用封装。基于 OpenAI 兼容接口。"""
from __future__ import annotations

from typing import Iterator

from openai import OpenAI

from config import config

_client: OpenAI | None = None


def _get_client() -> OpenAI:
    global _client
    if _client is None:
        _client = OpenAI(
            api_key=config.deepseek.api_key,
            base_url=config.deepseek.base_url,
        )
    return _client


def chat(
    prompt: str,
    system: str = "你是一名资深投研助理，输出专业、简洁、结构化。",
    temperature: float = 0.3,
    max_tokens: int = 2048,
) -> str:
    """同步对话：传入用户 prompt，返回模型回复文本。"""
    client = _get_client()
    resp = client.chat.completions.create(
        model=config.deepseek.model,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": prompt},
        ],
        temperature=temperature,
        max_tokens=max_tokens,
    )
    return resp.choices[0].message.content or ""


def chat_stream(
    prompt: str,
    system: str = "你是一名资深投研助理，输出专业、简洁、结构化。",
    temperature: float = 0.3,
    max_tokens: int = 2048,
) -> Iterator[str]:
    """流式对话：逐 token 返回。用于长文本生成时降低首字延迟。"""
    client = _get_client()
    stream = client.chat.completions.create(
        model=config.deepseek.model,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": prompt},
        ],
        temperature=temperature,
        max_tokens=max_tokens,
        stream=True,
    )
    for chunk in stream:
        delta = chunk.choices[0].delta.content
        if delta:
            yield delta
