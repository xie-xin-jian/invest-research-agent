"""Agent 运行常量（从原运维 Agent 的 platform.config 内联而来，按投研场景调整）。"""
from pathlib import Path

# 重试：429 限流 / 529 过载时指数退避
MAX_RETRIES = 4
MAX_CONSECUTIVE_529 = 3
BASE_DELAY_MS = 500
FALLBACK_MODEL_ID = ""  # 无备用模型，过载时只退避不切换

# 输出 token 上限：默认 4096，触顶后扩容到 8192 重试一次
DEFAULT_MAX_TOKENS = 4096
ESCALATED_MAX_TOKENS = 8192

# 上下文上限（字节粗估）：deepseek-chat 为 64K tokens，中文 1 字约 3 字节，
# 留足输出空间后取 100KB 作为压缩触发线
CONTEXT_LIMIT = 100_000

# 上下文压缩参数
KEEP_RECENT_TOOL_RESULTS = 3   # 最近 3 条工具结果保留原文，更早的替换为占位符
PERSIST_THRESHOLD = 20_000     # 单条工具结果超过 20KB 落盘，上下文里只留预览

# Agent 循环轮数上限：投研场景"搜→读→整理"3-6 轮足够，12 轮兜底防失控烧 token
MAX_TURNS = 12

# 大结果落盘 / 对话转录目录（不入 git）
_DATA_DIR = Path(__file__).resolve().parents[2] / ".agent_data"
TOOL_RESULTS_DIR = _DATA_DIR / "tool_results"
TRANSCRIPT_DIR = _DATA_DIR / "transcripts"
