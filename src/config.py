from __future__ import annotations

import os

try:
    import tomllib
except ImportError:
    import tomli as tomllib  # pip install tomli for Python < 3.11
from dataclasses import dataclass
from pathlib import Path

DEFAULT_CONFIG_FILE = Path(__file__).parent.parent / "bots.toml"


@dataclass
class BotConfig:
    project_path: str
    project_name: str
    # Platform: "telegram" or "qq"
    platform: str = "telegram"
    model: str = "claude-sonnet-4-6"
    chunk_size: int = 4000
    api_url: str | None = None   # ANTHROPIC_BASE_URL
    api_key: str | None = None   # ANTHROPIC_API_KEY
    # Telegram settings
    token: str | None = None
    allowed_user_id: int | None = None
    telegram_api_url: str | None = None  # CF Worker URL for Telegram API proxy
    telegram_api_key: str | None = None  # X-TCC-Key for CF Worker auth
    telegram_proxy: str | None = None    # SOCKS5/HTTP proxy for Telegram API
    # QQ settings
    qq_app_id: str | None = None
    qq_app_secret: str | None = None
    allowed_qq_openid: str | None = None        # C2C private message whitelist
    allowed_qq_group_openid: str | None = None  # Group message whitelist


def load() -> list[BotConfig]:
    config_path = Path(os.getenv("TCC_BRIDGE_CONFIG", str(DEFAULT_CONFIG_FILE))).expanduser()
    with open(config_path, "rb") as f:
        data = tomllib.load(f)
    return [BotConfig(**bot) for bot in data["bots"]]
