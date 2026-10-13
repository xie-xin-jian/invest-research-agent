"""工具注册表 + 执行器：Schema + Handler 二元组。

相比原运维 Agent 砍掉了 Policy / 审批 / Sandbox / bash 分流——
投研场景四个工具都是只读的（搜索、读文本、调模型），无风险操作，无需审批。
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable


@dataclass(frozen=True)
class ToolSpec:
    name: str
    schema: dict
    handler: Callable


class ToolRegistry:
    """工具名 → (给模型看的 schema, 实际执行的 handler)。"""

    def __init__(self):
        self._specs: dict[str, ToolSpec] = {}

    def register(self, schema: dict, handler: Callable) -> None:
        if not isinstance(schema, dict):
            raise TypeError("tool schema must be a dict")
        name = str(schema.get("name") or "").strip()
        if not name:
            raise ValueError("tool schema requires a name")
        if not callable(handler):
            raise TypeError(f"tool handler for '{name}' must be callable")
        self._specs[name] = ToolSpec(name=name, schema=schema, handler=handler)

    def get(self, name: str) -> ToolSpec | None:
        return self._specs.get(str(name or ""))

    def names(self) -> list[str]:
        return sorted(self._specs)

    def schemas(self) -> list[dict]:
        return [self._specs[name].schema for name in self.names()]


class ToolExecutor:
    """查注册表 → 调 handler → 异常兜成字符串回喂模型（模型可据此自我纠正）。"""

    def __init__(self, registry: ToolRegistry):
        self.registry = registry

    def execute(self, tool_name: str, tool_input: dict) -> str:
        if not isinstance(tool_input, dict):
            return f"Error: invalid input for tool '{tool_name}'"
        spec = self.registry.get(tool_name)
        if spec is None:
            return f"Error: no tool named '{tool_name}'"
        try:
            return str(spec.handler(**tool_input))
        except Exception as exc:
            return f"Error: {exc}"
