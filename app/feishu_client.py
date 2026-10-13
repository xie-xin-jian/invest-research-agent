"""飞书消息收发封装。

主要能力：
- 获取 tenant_access_token
- 回复文本 / 卡片消息
- 更新已发送的卡片（流式更新用）
"""
from __future__ import annotations

import time
from typing import Any

import httpx

from config import config

_BASE = "https://open.feishu.cn/open-apis"

_token_cache: dict[str, Any] = {"token": "", "expire_at": 0}


def get_tenant_access_token() -> str:
    """获取（带缓存）tenant_access_token。"""
    if _token_cache["token"] and time.time() < _token_cache["expire_at"] - 60:
        return _token_cache["token"]

    resp = httpx.post(
        f"{_BASE}/auth/v3/tenant_access_token/internal",
        json={
            "app_id": config.feishu.app_id,
            "app_secret": config.feishu.app_secret,
        },
        timeout=10,
    )
    resp.raise_for_status()
    data = resp.json()
    _token_cache["token"] = data["tenant_access_token"]
    _token_cache["expire_at"] = time.time() + data["expire"]
    return _token_cache["token"]


def _headers() -> dict[str, str]:
    return {"Authorization": f"Bearer {get_tenant_access_token()}"}


def reply_text(message_id: str, text: str) -> dict:
    """回复一条文本消息。"""
    resp = httpx.post(
        f"{_BASE}/im/v1/messages/{message_id}/reply",
        headers=_headers(),
        json={
            "content": json_dumps({"text": text}),
            "msg_type": "text",
        },
        timeout=10,
    )
    return resp.json()


def reply_card(message_id: str, card: dict) -> dict:
    """回复一条交互卡片消息。

    card 结构见飞书交互卡片文档：
    https://open.feishu.cn/document/uAjLw4CM/ukTMukTMukTM/feishu-cards/card-json-structure
    """
    resp = httpx.post(
        f"{_BASE}/im/v1/messages/{message_id}/reply",
        headers=_headers(),
        json={
            "content": json_dumps(card),
            "msg_type": "interactive",
        },
        timeout=10,
    )
    return resp.json()


def update_card(message_id: str, card: dict) -> dict:
    """更新已发送的卡片内容（用于流式输出渐进更新）。"""
    resp = httpx.patch(
        f"{_BASE}/im/v1/messages/{message_id}",
        headers=_headers(),
        json={
            "content": json_dumps(card),
            "msg_type": "interactive",
        },
        timeout=10,
    )
    return resp.json()


_bot_open_id: str = ""


def get_bot_open_id() -> str:
    """获取机器人自己的 open_id（带缓存）。用于群聊判断是否@了本机器人。"""
    global _bot_open_id
    if _bot_open_id:
        return _bot_open_id
    resp = httpx.get(f"{_BASE}/bot/v3/info", headers=_headers(), timeout=10)
    resp.raise_for_status()
    _bot_open_id = resp.json()["bot"]["open_id"]
    return _bot_open_id


def upload_file(data: bytes, file_name: str) -> str:
    """上传文件到飞书消息资源库，返回 file_key。需要 im:resource 权限。"""
    resp = httpx.post(
        f"{_BASE}/im/v1/files",
        headers=_headers(),
        data={"file_type": "stream", "file_name": file_name},
        files={"file": (file_name, data)},
        timeout=60,
    )
    resp.raise_for_status()
    body = resp.json()
    if body.get("code") != 0:
        raise RuntimeError(f"upload file failed: {body}")
    return body["data"]["file_key"]


def reply_file(message_id: str, file_key: str) -> dict:
    """回复一条文件消息。"""
    resp = httpx.post(
        f"{_BASE}/im/v1/messages/{message_id}/reply",
        headers=_headers(),
        json={
            "content": json_dumps({"file_key": file_key}),
            "msg_type": "file",
        },
        timeout=10,
    )
    return resp.json()


def download_file(message_id: str, file_key: str) -> bytes:
    """下载消息中的文件资源（用户发给机器人的附件）。

    文档：https://open.feishu.cn/document/uAjLw4CM/ukTMukTMukTM/reference/im-v1/message-resource/get
    """
    resp = httpx.get(
        f"{_BASE}/im/v1/messages/{message_id}/resources/{file_key}",
        headers=_headers(),
        params={"type": "file"},
        timeout=60,
    )
    resp.raise_for_status()
    return resp.content


def send_card(chat_id: str, card: dict) -> dict:
    """主动发送卡片消息到指定群（日报推送等场景，非回复）。"""
    resp = httpx.post(
        f"{_BASE}/im/v1/messages",
        headers=_headers(),
        params={"receive_id_type": "chat_id"},
        json={
            "receive_id": chat_id,
            "content": json_dumps(card),
            "msg_type": "interactive",
        },
        timeout=10,
    )
    return resp.json()


def json_dumps(obj: Any) -> str:
    import json

    return json.dumps(obj, ensure_ascii=False)
