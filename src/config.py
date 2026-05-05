import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN: str = os.environ["TELEGRAM_BOT_TOKEN"]
ALLOWED_USER_ID: int = int(os.environ["TELEGRAM_ALLOWED_USER_ID"])
PROJECT_PATH: str = os.environ["PROJECT_PATH"]
PROJECT_NAME: str = os.environ.get("PROJECT_NAME", Path(os.environ["PROJECT_PATH"]).name)
CC_MODEL: str = os.environ.get("CC_MODEL", "claude-sonnet-4-6")
CHUNK_SIZE: int = int(os.environ.get("MESSAGE_CHUNK_SIZE", "4000"))
