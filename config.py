"""配置加载：从环境变量读取飞书凭证和 DeepSeek 配置。"""
from __future__ import annotations

import os
from dataclasses import dataclass
from dotenv import load_dotenv

load_dotenv()


@dataclass
class FeishuConfig:
    app_id: str
    app_secret: str
    verification_token: str
    encrypt_key: str = ""


@dataclass
class DeepSeekConfig:
    api_key: str
    base_url: str
    model: str


@dataclass
class AppConfig:
    feishu: FeishuConfig
    deepseek: DeepSeekConfig
    port: int


def load_config() -> AppConfig:
    feishu = FeishuConfig(
        app_id=os.getenv("FEISHU_APP_ID", ""),
        app_secret=os.getenv("FEISHU_APP_SECRET", ""),
        verification_token=os.getenv("FEISHU_VERIFICATION_TOKEN", ""),
        encrypt_key=os.getenv("FEISHU_ENCRYPT_KEY", ""),
    )
    deepseek = DeepSeekConfig(
        api_key=os.getenv("DEEPSEEK_API_KEY", ""),
        base_url=os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com"),
        model=os.getenv("DEEPSEEK_MODEL", "deepseek-chat"),
    )
    port = int(os.getenv("PORT", "8000"))
    return AppConfig(feishu=feishu, deepseek=deepseek, port=port)


config = load_config()
