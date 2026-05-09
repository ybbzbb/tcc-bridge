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
    platform: str = "qq"
    model: str = "claude-sonnet-4-6"
    chunk_size: int = 4000
    api_url: str | None = None   # ANTHROPIC_BASE_URL
    api_key: str | None = None   # ANTHROPIC_API_KEY
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
