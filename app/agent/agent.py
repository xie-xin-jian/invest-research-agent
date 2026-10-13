"""ResearchAgent：组装 Anthropic client + 工具注册表 + 运行循环。

技术路线：DeepSeek 提供 Anthropic 兼容端点，直接复用 Anthropic SDK 的
tool-use block 协议，Agent 基建（pipeline/tool_loop）几乎零改动可用。
"""
from __future__ import annotations

from anthropic import Anthropic

from app.agent.error_recovery import RecoveryState
from app.agent.memory import MemoryStore
from app.agent.pipeline import PipelineMixin
from app.agent.tool_loop import ToolLoopMixin
from app.agent.tool_specs import register_research_tools
from app.agent.tools import ToolExecutor, ToolRegistry
from config import config

# 全局唯一记忆库（JSON 文件，进程内单例共享）
memory_store = MemoryStore()


class ResearchAgent(ToolLoopMixin, PipelineMixin):
    """一次用户提问创建一个实例；user_scope 非空时启用用户级记忆。"""

    def __init__(self, user_scope: str = ""):
        self.client = Anthropic(
            api_key=config.deepseek.api_key,
            base_url=config.deepseek.anthropic_base_url,
        )
        self.messages: list = []
        self.recovery = RecoveryState(model=config.deepseek.model)
        self.registry = ToolRegistry()
        register_research_tools(self.registry)
        self.tool_executor = ToolExecutor(self.registry)
        self.current_run_id = ""
        self.user_scope = user_scope
        self.memory_store = memory_store if user_scope else None
        self._memory_context = ""
