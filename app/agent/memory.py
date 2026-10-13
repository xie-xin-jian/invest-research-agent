"""用户级对话记忆：JSON 文件存储 + 关键词检索（CJK bigram + Jaccard 相似度）。

投研场景的用法：
- 每个飞书用户一个独立 scope（user:{open_id}），互相隔离
- 每轮问答结束后存一条 "Q: ... A: ..." 摘要
- 新提问时按关键词相似度检索 top-k 注入 system prompt，模型据此知道用户之前关心过什么

从原运维 Agent 的 memory 模块简化而来：砍掉 entity/importance/confidence/
access 等多维打分（投研初期用不上），保留核心的分词与相似度逻辑。
"""
from __future__ import annotations

import hashlib
import json
import re
import threading
import time
import unicodedata
from pathlib import Path

from app.agent.constants import _DATA_DIR

_LATIN_TOKEN_RE = re.compile(r"[a-z0-9][a-z0-9_.:/-]*")
_CJK_SEQUENCE_RE = re.compile(r"[㐀-䶿一-鿿]+")

_LOCK = threading.RLock()
_MAX_PER_SCOPE = 200      # 每个用户最多保留的记忆条数，超出按时间淘汰
_MIN_SCORE = 0.15         # 检索最低相关分，低于此分不注入（防止噪音污染 prompt）


def _normalize(text: str) -> str:
    return re.sub(r"\s+", " ", unicodedata.normalize("NFKC", str(text))).strip()


def _tokenize(text: str) -> set[str]:
    """拉丁词干 + 中文 bigram 分词。"""
    normalized = _normalize(text).lower()
    tokens = set(_LATIN_TOKEN_RE.findall(normalized))
    for seq in _CJK_SEQUENCE_RE.findall(normalized):
        tokens.add(seq)
        for i in range(len(seq) - 1):
            tokens.add(seq[i : i + 2])
    return {t for t in tokens if t}


def _score(query: str, query_tokens: set[str], content: str, created_at: float) -> float:
    if not query_tokens:
        return 0.0
    content_lower = _normalize(content).lower()
    query_lower = _normalize(query).lower()
    phrase = 1.0 if query_lower and query_lower in content_lower else 0.0
    overlap = len(query_tokens & _tokenize(content)) / len(query_tokens)
    lexical = min(1.0, phrase * 0.35 + overlap * 0.65)
    if lexical <= 0:
        return 0.0
    # 时间衰减：30 天半衰期，轻微影响排序
    age_days = max(0.0, (time.time() - created_at) / 86400)
    recency = 2.718281828 ** (-age_days / 30)
    return lexical * 0.9 + recency * 0.1


class MemoryStore:
    """单进程 JSON 文件记忆库。线程安全（RLock），写时整文件覆盖。"""

    def __init__(self, path: Path | None = None):
        self._path = path or (_DATA_DIR / "memories.json")
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._memories: list[dict] = []
        self._load()

    def _load(self) -> None:
        if not self._path.exists():
            return
        try:
            with open(self._path, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, list):
                self._memories = [m for m in data if isinstance(m, dict) and m.get("content")]
        except (json.JSONDecodeError, OSError):
            self._memories = []

    def _save(self) -> None:
        tmp = self._path.with_suffix(".tmp")
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(self._memories, f, ensure_ascii=False, indent=1)
        tmp.replace(self._path)

    @staticmethod
    def _hash(scope: str, content: str) -> str:
        return hashlib.sha256(f"{scope}|{_normalize(content).lower()}".encode("utf-8")).hexdigest()

    def add(self, scope: str, content: str, kind: str = "qa") -> None:
        """写入一条记忆；同 scope 同内容去重（刷新时间），超上限按最旧淘汰。"""
        content = _normalize(content)
        if not scope or not content:
            return
        with _LOCK:
            h = self._hash(scope, content)
            for m in self._memories:
                if m.get("hash") == h:
                    m["updated_at"] = time.time()
                    self._save()
                    return
            now = time.time()
            self._memories.append(
                {
                    "hash": h,
                    "scope": scope,
                    "kind": kind,
                    "content": content,
                    "created_at": now,
                    "updated_at": now,
                }
            )
            scoped = [m for m in self._memories if m["scope"] == scope]
            if len(scoped) > _MAX_PER_SCOPE:
                overflow = len(scoped) - _MAX_PER_SCOPE
                scoped.sort(key=lambda m: m["updated_at"])
                drop = {id(m) for m in scoped[:overflow]}
                self._memories = [m for m in self._memories if id(m) not in drop]
            self._save()

    def select(self, query: str, scope: str, top_k: int = 3) -> list[dict]:
        """按关键词相似度检索该用户的 top-k 相关记忆。"""
        with _LOCK:
            query_tokens = _tokenize(query)
            scored = []
            for m in self._memories:
                if m.get("scope") != scope:
                    continue
                s = _score(query, query_tokens, m.get("content", ""), m.get("updated_at", 0.0))
                if s >= _MIN_SCORE:
                    scored.append((s, m))
            scored.sort(key=lambda x: x[0], reverse=True)
            return [m for _, m in scored[:top_k]]

    @staticmethod
    def format(memories: list[dict]) -> str:
        if not memories:
            return ""
        return "\n".join(f"[{i}] {m['content']}" for i, m in enumerate(memories, 1))
