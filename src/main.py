import asyncio
import logging
import signal
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("telegram").setLevel(logging.WARNING)
log = logging.getLogger(__name__)

import config
from bot import TelegramBot


async def run() -> None:
    configs = config.load()
    if not configs:
        log.error("No bots configured in bots.toml")
        return

    bots = [TelegramBot(cfg) for cfg in configs]

    stop_event = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, stop_event.set)

    for bot in bots:
        await bot.start()

    log.info("%d bot(s) running. Press Ctrl+C to stop.", len(bots))
    await stop_event.wait()

    for bot in reversed(bots):
        await bot.stop()


if __name__ == "__main__":
    asyncio.run(run())
