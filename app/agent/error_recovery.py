"""错误恢复：429 限流指数退避重试、上下文超长恢复、输出 token 触顶扩容。"""
from __future__ import annotations

import random
import time

from app.agent import context_compact
from app.agent.constants import (
    BASE_DELAY_MS,
    CONTEXT_LIMIT,
    DEFAULT_MAX_TOKENS,
    ESCALATED_MAX_TOKENS,
    MAX_CONSECUTIVE_529,
    MAX_RETRIES,
)


class RecoveryState:
    """一次 Agent 运行期间的可变恢复状态。"""

    def __init__(self, model: str, max_tokens: int = DEFAULT_MAX_TOKENS):
        self.has_escalated = False
        self.recovery_count = 0
        self.consecutive_529 = 0
        self.current_model = model
        self.current_max_tokens = max_tokens


def retry_delay(attempt: int) -> float:
    base = min(BASE_DELAY_MS * (2**attempt), 32000) / 1000
    return base + random.uniform(0, base * 0.25)


def with_retry(fn, state: RecoveryState):
    """429/529 时指数退避重试，其余异常直接抛出。"""
    for attempt in range(MAX_RETRIES):
        try:
            result = fn()
            state.consecutive_529 = 0
            return result
        except Exception as e:
            name = type(e).__name__.lower()
            msg = str(e).lower()
            if "ratelimit" in name or "429" in msg:
                if attempt < MAX_RETRIES - 1:
                    time.sleep(retry_delay(attempt))
                    continue
            if "overloaded" in name or "529" in msg or "overloaded" in msg:
                state.consecutive_529 += 1
                if attempt < MAX_RETRIES - 1:
                    time.sleep(retry_delay(attempt))
                    continue
            raise
    raise RuntimeError(f"Max retries ({MAX_RETRIES}) exceeded")


def is_prompt_too_long_error(e: Exception) -> bool:
    msg = str(e).lower()
    return (
        ("prompt" in msg and "long" in msg)
        or "context_length_exceeded" in msg
        or "max_context_window" in msg
    )


def is_output_limit_error(e: Exception) -> bool:
    """模型服务拒绝了请求的输出长度。"""
    msg = str(e).lower()
    return any(
        marker in msg
        for marker in (
            "max_tokens",
            "max output",
            "maximum output",
            "output token",
            "output length",
            "completion token",
        )
    )


def recover_context_overflow(
    messages: list,
    client,
    model,
    context_limit: int | None = None,
) -> tuple[list, dict]:
    """上下文超长时的三级恢复：大结果落盘 → 旧结果占位 → 模型摘要 → 中间裁剪。"""
    limit = CONTEXT_LIMIT if context_limit is None else context_limit
    before = context_compact.estimate_size(messages)

    recovered = context_compact.tool_result_budget(messages)
    recovered = context_compact.micro_compact(recovered)
    recovered = context_compact.reactive_compact(recovered, client, model)

    after_reactive = context_compact.estimate_size(recovered)
    if after_reactive >= before * 0.9:
        recovered = context_compact.snip_compact(recovered)

    after = context_compact.estimate_size(recovered)
    stats = {
        "before": before,
        "after": after,
        "after_reactive": after_reactive,
        "limit": limit,
        "reduced": after < before * 0.9,
        "within_limit": after <= limit,
    }
    return recovered, stats


def escalate_tokens(state: RecoveryState) -> bool:
    if state.current_max_tokens < ESCALATED_MAX_TOKENS:
        state.current_max_tokens = ESCALATED_MAX_TOKENS
        state.has_escalated = True
        return True
    return False
