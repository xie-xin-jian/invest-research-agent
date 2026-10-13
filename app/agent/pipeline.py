"""Agent 推理主循环：调模型 → 有 tool_use 就执行并回喂 → 直到模型输出纯文本。

事件流（每步 yield 一个 dict）：
  {"type": "status", "message": str, "turn": int}      进度提示
  {"type": "tool_use", "tool": str, "input": dict, "turn": int}
  {"type": "tool_result", "tool": str, "duration_ms": int, "turn": int}
  {"type": "text_delta", "delta": str}                 最终回答的流式切片
  {"type": "done", "text": str, "total_turns": int}
  {"type": "error", "message": str}

相比原运维 Agent 砍掉：审批流、审计、运行状态持久化、Sandbox、后台任务收集。
"""
from __future__ import annotations

import logging
import time
import uuid

from app.agent.constants import CONTEXT_LIMIT, MAX_TURNS
from app.agent.context_compact import (
    compact_history,
    estimate_size,
    micro_compact,
    tool_result_budget,
)
from app.agent.error_recovery import (
    escalate_tokens,
    is_output_limit_error,
    is_prompt_too_long_error,
    recover_context_overflow,
)

logger = logging.getLogger("feishu-bot")


def extract_text(content) -> str:
    """从模型的 content blocks 里拼出纯文本部分。"""
    parts = []
    for block in content:
        btype = block.get("type") if isinstance(block, dict) else getattr(block, "type", "")
        if btype == "text":
            parts.append(
                block.get("text", "") if isinstance(block, dict) else getattr(block, "text", "")
            )
    return "".join(parts)


def has_tool_use(content) -> bool:
    for block in content:
        btype = block.get("type") if isinstance(block, dict) else getattr(block, "type", "")
        if btype == "tool_use":
            return True
    return False


class PipelineMixin:
    def run(self, user_message: str) -> str:
        """同步执行（收集全部事件，返回最终文本）。"""
        final_text = ""
        for event in self.run_stream(user_message):
            if event["type"] in ("done", "cancelled"):
                final_text = event["text"]
            elif event["type"] == "error":
                raise RuntimeError(event["message"])
        return final_text

    def run_stream(self, user_message: str):
        """流式执行 Agent 循环，逐事件 yield。"""
        self.current_run_id = f"run_{uuid.uuid4().hex}"
        self.messages.append({"role": "user", "content": user_message})
        logger.info("[user] %s", user_message[:200])

        yield {"type": "status", "message": "准备中...", "turn": 0}

        final_text = ""
        context_recovery_attempts = 0
        max_context_recovery_attempts = 2

        for turn in range(MAX_TURNS):
            # 每轮开头：上下文快满时先做轻量压缩
            if estimate_size(self.messages) > CONTEXT_LIMIT:
                self.messages = tool_result_budget(self.messages)
                self.messages = micro_compact(self.messages)

            logger.info(
                "[turn %d] 调用 %s (ctx %d bytes)",
                turn + 1,
                self.recovery.current_model,
                estimate_size(self.messages),
            )

            try:
                response = self._call_api(self.messages)
            except Exception as e:
                if is_prompt_too_long_error(e):
                    if context_recovery_attempts >= max_context_recovery_attempts:
                        yield {"type": "error", "message": "上下文压缩后仍然超过模型限制"}
                        return
                    context_recovery_attempts += 1
                    yield {
                        "type": "status",
                        "message": "上下文过长，压缩后重试...",
                        "turn": turn + 1,
                    }
                    try:
                        compacted, stats = recover_context_overflow(
                            self.messages,
                            self.client,
                            self.recovery.current_model,
                        )
                    except Exception as compact_error:
                        yield {"type": "error", "message": f"上下文压缩失败: {compact_error}"}
                        return
                    self.messages = compacted
                    logger.info(
                        "[turn %d] context recovery: %d -> %d bytes",
                        turn + 1, stats["before"], stats["after"],
                    )
                    if not stats["reduced"]:
                        yield {"type": "error", "message": "上下文压缩未有效缩小输入，无法继续"}
                        return
                    continue

                if is_output_limit_error(e) and escalate_tokens(self.recovery):
                    yield {
                        "type": "status",
                        "message": f"输出上限扩容到 {self.recovery.current_max_tokens}",
                        "turn": turn + 1,
                    }
                    continue

                logger.exception("[turn %d] API 异常", turn + 1)
                yield {"type": "error", "message": str(e)}
                return

            self.messages.append({"role": "assistant", "content": response.content})

            if not has_tool_use(response.content):
                # 模型认为不需要调工具了 → 输出最终文字
                final_text = extract_text(response.content)
                logger.info("[turn %d] 完成: %d 字符", turn + 1, len(final_text or ""))
                # 伪流式：按大段切片，配合前端 1s 节流，视觉上有渐进感但不拖沓
                step = 40
                for i in range(0, len(final_text), step):
                    yield {"type": "text_delta", "delta": final_text[i : i + step]}
                break

            # 执行本轮所有工具调用（模型可能一次发多个 tool_use）
            results = []
            for block in response.content:
                btype = block.get("type") if isinstance(block, dict) else getattr(block, "type", "")
                if btype != "tool_use":
                    continue
                name = block.get("name") if isinstance(block, dict) else block.name
                block_id = block.get("id") if isinstance(block, dict) else block.id
                block_input = block.get("input") if isinstance(block, dict) else block.input
                tool_input = block_input if isinstance(block_input, dict) else {"input": str(block_input)}

                logger.info("[turn %d] tool_use: %s %s", turn + 1, name, str(tool_input)[:120])
                yield {"type": "tool_use", "tool": name, "input": tool_input, "turn": turn + 1}

                t0 = time.time()
                try:
                    output = self.tool_executor.execute(name, tool_input)
                except Exception as tool_err:
                    output = f"Error: {tool_err}"
                    logger.error("[turn %d] tool %s 异常: %s", turn + 1, name, tool_err)
                duration_ms = int((time.time() - t0) * 1000)
                logger.info("[turn %d] tool_done: %s (%dms)", turn + 1, name, duration_ms)

                yield {
                    "type": "tool_result",
                    "tool": name,
                    "duration_ms": duration_ms,
                    "turn": turn + 1,
                }
                results.append(
                    {"type": "tool_result", "tool_use_id": block_id, "content": str(output)}
                )

            # 工具结果回喂模型，进入下一轮
            self.messages.append({"role": "user", "content": results})

        if not final_text:
            for msg in reversed(self.messages):
                if msg["role"] == "assistant":
                    final_text = extract_text(msg["content"])
                    if final_text:
                        break

        # 会话保存：保留最近对话历史，下次同用户提问时恢复（多轮上下文）
        _save_session_scope = getattr(self, "user_scope", "")
        if _save_session_scope:
            from app.agent.agent import _save_session
            _save_session(_save_session_scope, self.messages)

        yield {"type": "done", "text": final_text or "", "total_turns": turn + 1}
