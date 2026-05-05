from __future__ import annotations

import asyncio
import logging
import os
import time
from typing import AsyncIterator

log = logging.getLogger(__name__)

MAX_RESPONSE = 600.0  # 10 min hard cap per message
IDLE_TIMEOUT = 2.0    # seconds of silence before flushing a chunk to Telegram


class CCSession:
    def __init__(self, project_path: str, model: str,
                 api_url: str | None = None, api_key: str | None = None):
        self.project_path = project_path
        self.model = model
        self.api_url = api_url
        self.api_key = api_key
        self._busy = False
        self._started_at: float | None = None

    def _build_env(self) -> dict:
        env = os.environ.copy()
        if self.api_url:
            env["ANTHROPIC_BASE_URL"] = self.api_url
        if self.api_key:
            env["ANTHROPIC_API_KEY"] = self.api_key
        return env

    @property
    def is_running(self) -> bool:
        return self._started_at is not None

    @property
    def is_busy(self) -> bool:
        return self._busy

    @property
    def uptime(self) -> str:
        if self._started_at is None:
            return "N/A"
        s = int(time.time() - self._started_at)
        return f"{s // 3600:02d}:{(s % 3600) // 60:02d}:{s % 60:02d}"

    def start(self) -> None:
        self._started_at = time.time()

    def stop(self) -> None:
        self._started_at = None
        self._busy = False

    def restart(self) -> None:
        self.stop()
        self.start()

    async def send_message(self, text: str) -> AsyncIterator[str]:
        """Set busy flag and return a streaming async iterator of output chunks."""
        if not self.is_running:
            raise RuntimeError("Session is not running")
        if self._busy:
            raise RuntimeError("Session is busy")
        self._busy = True
        return self._stream(text)

    async def _stream(self, text: str) -> AsyncIterator[str]:
        cmd = [
            "claude", "--print", "--continue",
            "--dangerously-skip-permissions",
            "--model", self.model,
        ]
        log.info(">>> [%s] %s", self.project_path, text[:200])
        log.info("CMD %s", " ".join(cmd))

        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
            cwd=self.project_path,
            env=self._build_env(),
        )

        proc.stdin.write(text.encode())
        await proc.stdin.drain()
        proc.stdin.close()

        buffer: list[str] = []
        total_chars = 0
        loop = asyncio.get_event_loop()
        deadline = loop.time() + MAX_RESPONSE

        try:
            while True:
                remaining = deadline - loop.time()
                if remaining <= 0:
                    proc.kill()
                    raise RuntimeError("CC response timed out (10 min)")

                try:
                    data = await asyncio.wait_for(
                        proc.stdout.read(4096),
                        timeout=min(IDLE_TIMEOUT, remaining),
                    )
                    if not data:  # EOF — process finished
                        break
                    decoded = data.decode("utf-8", errors="replace")
                    buffer.append(decoded)
                    total_chars += len(decoded)

                except asyncio.TimeoutError:
                    if buffer:
                        chunk = "".join(buffer)
                        buffer = []
                        log.debug("CHUNK %d chars (idle flush)", len(chunk))
                        yield chunk

            if buffer:
                chunk = "".join(buffer)
                log.debug("CHUNK %d chars (final)", len(chunk))
                yield chunk

            await proc.wait()
            log.info("<<< [exit=%d] %d total chars", proc.returncode, total_chars)

            if proc.returncode != 0:
                raise RuntimeError(f"CC exited with code {proc.returncode}")

        finally:
            self._busy = False
