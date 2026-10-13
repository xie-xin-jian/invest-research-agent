"""ResearchAgent：组装 Anthropic client + 工具注册表 + 运行循环。

技术路线：DeepSeek 提供 Anthropic 兼容端点，直接复用 Anthropic SDK 的
tool-use block 协议，Agent 基建（pipeline/tool_loop）几乎零改动可用。
"""
from __future__ import annotations

import time
from anthropic import Anthropic

from app.agent.error_recovery import RecoveryState
from app.agent.pipeline import PipelineMixin
from app.agent.tool_loop import ToolLoopMixin
from app.agent.tool_specs import register_research_tools
from app.agent.tools import ToolExecutor, ToolRegistry
from config import config

# 会话缓存：按 user_scope 存最近对话历史，使模型能看到上下文（"第一条吧"能对上）
# 限制：每用户最多 30 条消息，超过 30 分钟未活动自动清空
_sessions: dict[str, dict] = {}
_SESSION_MAX_MSGS = 30
_SESSION_TTL = 1800  # 30 分钟


class ResearchAgent(ToolLoopMixin, PipelineMixin):
    """一次用户提问创建一个实例；user_scope 非空时恢复该用户最近对话历史。"""

    def __init__(self, user_scope: str = "", chat_id: str = ""):
        self.client = Anthropic(
            api_key=config.deepseek.api_key,
            base_url=config.deepseek.anthropic_base_url,
        )
        # 从会话缓存恢复最近对话（让模型能理解"第一条吧"这种上下文指代）
        self.messages: list = _restore_session(user_scope)
        self.recovery = RecoveryState(model=config.deepseek.model)
        self.registry = ToolRegistry()
        register_research_tools(self.registry, chat_id=chat_id)
        self.tool_executor = ToolExecutor(self.registry)
        self.current_run_id = ""
        self.user_scope = user_scope


def _restore_session(scope: str) -> list:
    """恢复该用户的最近对话历史；过期或不存在则返回空列表。"""
    if not scope:
        return []
    record = _sessions.get(scope)
    if record is None:
        return []
    if time.time() - record["ts"] > _SESSION_TTL:
        del _sessions[scope]
        return []
    msgs = list(record["messages"])
    return msgs


def _save_session(scope: str, messages: list) -> None:
    """保存该用户本轮结束后的完整对话历史（截断到最近 N 条）。"""
    if not scope:
        return
    if len(messages) > _SESSION_MAX_MSGS:
        messages = messages[-_SESSION_MAX_MSGS:]
    _sessions[scope] = {"messages": messages, "ts": time.time()}
