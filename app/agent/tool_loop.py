"""API 调用封装：每次调模型前修复 tool_use/tool_result 消息配对。

为什么需要修复：如果上一轮运行被中断（异常、超时），messages 里可能留下
一个没有对应 tool_result 的 tool_use，Anthropic API 会直接报 400。
"""
from __future__ import annotations

from app.agent.context_manager import build_system_prompt
from app.agent.error_recovery import with_retry


class ToolLoopMixin:
    def _repair_message_sequence(self, messages: list) -> list:
        """Ensure each tool_use has its tool_result in the immediately next user message."""
        if not messages:
            return messages

        def _value(block, name, default=None):
            if isinstance(block, dict):
                return block.get(name, default)
            return getattr(block, name, default)

        def _is_type(block, block_type: str) -> bool:
            return str(_value(block, "type", "") or "") == block_type

        def _merge_content(existing, repair_blocks: list[dict]) -> list:
            if isinstance(existing, list):
                return repair_blocks + list(existing)
            if isinstance(existing, str) and existing:
                return repair_blocks + [{"type": "text", "text": existing}]
            return repair_blocks

        def _repair_blocks(missing_ids: list[str]) -> list[dict]:
            return [
                {
                    "type": "tool_result",
                    "tool_use_id": tool_use_id,
                    "content": (
                        "Error: the previous tool call was interrupted "
                        "before a result was produced."
                    ),
                }
                for tool_use_id in missing_ids
            ]

        repaired: list = []
        changed = False
        index = 0
        while index < len(messages):
            msg = messages[index]
            repaired.append(msg)
            if msg.get("role") != "assistant":
                index += 1
                continue
            content = msg.get("content")
            if not isinstance(content, list):
                index += 1
                continue
            tool_use_ids = [
                str(_value(block, "id", "") or "")
                for block in content
                if _is_type(block, "tool_use") and _value(block, "id")
            ]
            if not tool_use_ids:
                index += 1
                continue

            next_message = (
                messages[index + 1]
                if index + 1 < len(messages)
                else None
            )
            existing_result_ids: set[str] = set()
            if (
                next_message is not None
                and next_message.get("role") == "user"
                and isinstance(next_message.get("content"), list)
            ):
                existing_result_ids = {
                    str(_value(block, "tool_use_id", "") or "")
                    for block in next_message["content"]
                    if _is_type(block, "tool_result")
                    and _value(block, "tool_use_id")
                }
            missing_ids = [
                tool_use_id
                for tool_use_id in tool_use_ids
                if tool_use_id not in existing_result_ids
            ]
            if not missing_ids:
                index += 1
                continue

            repair_blocks = _repair_blocks(missing_ids)
            changed = True
            if next_message is not None and next_message.get("role") == "user":
                merged = dict(next_message)
                merged["content"] = _merge_content(
                    next_message.get("content"),
                    repair_blocks,
                )
                repaired.append(merged)
                index += 2
            else:
                repaired.append({"role": "user", "content": repair_blocks})
                index += 1

        return repaired if changed else messages

    def _call_api(self, messages: list):
        # 修复可能因中断导致的 tool_use/tool_result 不配对
        repaired = self._repair_message_sequence(messages)
        if repaired is not messages:
            self.messages = repaired
            messages = repaired

        def _call():
            return self.client.messages.create(
                model=self.recovery.current_model,
                system=build_system_prompt(getattr(self, "_memory_context", "")),
                messages=messages,
                tools=self.registry.schemas(),
                max_tokens=self.recovery.current_max_tokens,
            )

        return with_retry(_call, self.recovery)
