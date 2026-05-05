import tomllib
from dataclasses import dataclass, field
from pathlib import Path

CONFIG_FILE = Path(__file__).parent.parent / "bots.toml"


@dataclass
class BotConfig:
    token: str
    allowed_user_id: int
    project_path: str
    project_name: str
    model: str = "claude-sonnet-4-6"
    chunk_size: int = 4000
    api_url: str | None = None   # ANTHROPIC_BASE_URL passed to CC subprocess
    api_key: str | None = None   # ANTHROPIC_API_KEY passed to CC subprocess


def load() -> list[BotConfig]:
    with open(CONFIG_FILE, "rb") as f:
        data = tomllib.load(f)
    return [BotConfig(**bot) for bot in data["bots"]]
