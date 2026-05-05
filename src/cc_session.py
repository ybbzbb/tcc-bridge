import asyncio
import logging
import os
import time
from enum import Enum

log = logging.getLogger(__name__)

IDLE_TIMEOUT = 3.0    # seconds of output silence → response done
STARTUP_IDLE = 3.0    # seconds of silence → CC ready after startup
STARTUP_MAX = 15.0    # max seconds to wait during startup
MAX_RESPONSE = 600.0  # 10 min hard cap per response


class State(Enum):
    STOPPED = "stopped"
    RUNNING = "running"


class CCSession:
    def __init__(self, project_path: str, model: str,
                 api_url: str | None = None, api_key: str | None = None):
        self.project_path = project_path
        self.model = model
        self.api_url = api_url
        self.api_key = api_key
        self.state = State.STOPPED
        self._proc: asyncio.subprocess.Process | None = None
        self._busy = False
        self._started_at: float | None = None

    def _build_env(self) -> dict:
        env = os.environ.copy()
        if self.api_url:
            env["ANTHROPIC_BASE_URL"] = self.api_url
        if self.api_key:
            env["ANTHROPIC_API_KEY"] = self.api_key
        return env

    async def start(self) -> None:
        if self.state == State.RUNNING:
            raise RuntimeError("Already running")
        self._proc = await asyncio.create_subprocess_exec(
            "claude",
            "--dangerously-skip-permissions",
            "--model", self.model,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
            cwd=self.project_path,
            env=self._build_env(),
        )
        self._started_at = time.time()
        # Drain the startup banner before marking as ready
        await self._read_until_idle(STARTUP_IDLE, STARTUP_MAX)
        self.state = State.RUNNING
        log.info("CC session started (pid=%d)", self._proc.pid)

    async def stop(self) -> None:
        self.state = State.STOPPED
        self._busy = False
        if self._proc and self._proc.returncode is None:
            self._proc.terminate()
            try:
                await asyncio.wait_for(self._proc.wait(), timeout=5)
            except asyncio.TimeoutError:
                self._proc.kill()
        self._proc = None
        self._started_at = None
        log.info("CC session stopped")

    async def restart(self) -> None:
        await self.stop()
        await self.start()

    async def send_message(self, text: str) -> str:
        if self.state != State.RUNNING:
            raise RuntimeError("Session is not running")
        if self._busy:
            raise RuntimeError("Session is busy")
        if self._proc is None or self._proc.returncode is not None:
            self.state = State.STOPPED
            raise RuntimeError("CC process is not alive")

        self._busy = True
        try:
            self._proc.stdin.write((text + "\n").encode())
            await self._proc.stdin.drain()
            return await self._read_until_idle(IDLE_TIMEOUT, MAX_RESPONSE)
        finally:
            self._busy = False

    async def _read_until_idle(self, idle: float, max_wait: float) -> str:
        chunks: list[str] = []
        loop = asyncio.get_event_loop()
        deadline = loop.time() + max_wait
        while True:
            remaining = deadline - loop.time()
            if remaining <= 0:
                break
            try:
                data = await asyncio.wait_for(
                    self._proc.stdout.read(4096),
                    timeout=min(idle, remaining),
                )
                if not data:  # EOF — process died
                    if self.state == State.RUNNING:
                        self.state = State.STOPPED
                    break
                chunks.append(data.decode("utf-8", errors="replace"))
            except asyncio.TimeoutError:
                break  # idle timeout → response complete
        return "".join(chunks)

    @property
    def is_busy(self) -> bool:
        return self._busy

    @property
    def uptime(self) -> str:
        if self._started_at is None:
            return "N/A"
        s = int(time.time() - self._started_at)
        return f"{s // 3600:02d}:{(s % 3600) // 60:02d}:{s % 60:02d}"
