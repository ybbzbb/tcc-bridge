from __future__ import annotations

import asyncio
import logging
import os
import time
from typing import AsyncIterator

log = logging.getLogger(__name__)

MAX_RESPONSE = 600.0     # 10 min hard cap per message
IDLE_SHUTDOWN = 30 * 60  # 30 min no messages → auto-stop


class CCSession:
    def __init__(self, project_path: str, model: str,
                 api_url: str | None = None, api_key: str | None = None):
        self.project_path = project_path
        self.model = model
        self.api_url = api_url
        self.api_key = api_key
        self._proc: asyncio.subprocess.Process | None = None
        self._busy = False
        self._busy_since: float | None = None
        self._cancelled = False
        self._started_at: float | None = None
        self._idle_task: asyncio.Task | None = None

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
    def busy_elapsed(self) -> int:
        if self._busy_since is None:
            return 0
        return int(time.time() - self._busy_since)

    @property
    def was_cancelled(self) -> bool:
        return self._cancelled

    @property
    def uptime(self) -> str:
        if self._started_at is None:
            return "N/A"
        s = int(time.time() - self._started_at)
        return f"{s // 3600:02d}:{(s % 3600) // 60:02d}:{s % 60:02d}"

    def cancel(self) -> None:
        self._cancelled = True
        if self._proc and self._proc.returncode is None:
            self._proc.kill()

    def start(self) -> None:
        self._started_at = time.time()
        self._reset_idle()

    def stop(self) -> None:
        self._started_at = None
        self._busy = False
        self._busy_since = None
        self._cancel_idle()
        if self._proc and self._proc.returncode is None:
            self._proc.kill()
        self._proc = None

    def restart(self) -> None:
        self.stop()
        self.start()

    def _reset_idle(self) -> None:
        self._cancel_idle()
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            return
        self._idle_task = loop.create_task(self._idle_monitor())

    def _cancel_idle(self) -> None:
        if self._idle_task and not self._idle_task.done():
            self._idle_task.cancel()
        self._idle_task = None

    async def _idle_monitor(self) -> None:
        try:
            await asyncio.sleep(IDLE_SHUTDOWN)
            log.info("[%s] Idle 30 min, auto-stopping session", self.project_path)
            self.stop()
        except asyncio.CancelledError:
            pass

    async def send_message(self, text: str) -> AsyncIterator[str]:
        if not self.is_running:
            raise RuntimeError("Session is not running")
        if self._busy:
            raise RuntimeError("Session is busy")
        self._busy = True
        self._busy_since = time.time()
        self._cancelled = False
        return self._stream(text)

    async def _stream(self, text: str) -> AsyncIterator[str]:
        try:
            cmd = ["claude", "--dangerously-skip-permissions",
                   "--model", self.model, "--print", "--continue"]
            log.info(">>> [%s] %s", self.project_path, text[:200])

            self._proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=self.project_path,
                env=self._build_env(),
            )
            self._proc.stdin.write(text.encode() + b"\n")
            await self._proc.stdin.drain()
            self._proc.stdin.close()

            total_chars = 0
            stderr_chunks: list[bytes] = []
            loop = asyncio.get_running_loop()
            deadline = loop.time() + MAX_RESPONSE
            start_time = loop.time()
            last_heartbeat = start_time

            async def _read_stderr() -> None:
                while True:
                    chunk = await self._proc.stderr.read(4096)
                    if not chunk:
                        break
                    stderr_chunks.append(chunk)

            stderr_task = loop.create_task(_read_stderr())

            while True:
                remaining = deadline - loop.time()
                if remaining <= 0:
                    self._proc.kill()
                    raise RuntimeError("Response timed out (10 min)")

                try:
                    data = await asyncio.wait_for(
                        self._proc.stdout.read(4096),
                        timeout=min(10.0, remaining),
                    )
                    if not data:
                        break  # EOF = process finished
                    decoded = data.decode("utf-8", errors="replace")
                    total_chars += len(decoded)
                    yield decoded

                    now = loop.time()
                    if now - last_heartbeat >= 10:
                        log.info("... CC running (%.0fs elapsed)", now - start_time)
                        last_heartbeat = now

                except asyncio.TimeoutError:
                    now = loop.time()
                    if now - last_heartbeat >= 10:
                        log.info("... waiting for CC response (%.0fs)", now - start_time)
                        last_heartbeat = now

            await self._proc.wait()
            await stderr_task
            if self._proc.returncode not in (0, -9):  # -9 = SIGKILL (cancelled)
                stderr_text = b"".join(stderr_chunks).decode("utf-8", errors="replace").strip()
                log.error("CC exited with code %d, stderr: %s", self._proc.returncode, stderr_text[:500])
                raise RuntimeError(f"CC exited with code {self._proc.returncode}\n{stderr_text[:200]}")

            if not self._cancelled:
                log.info("<<< [%s] done, %d chars received", self.project_path, total_chars)
                self._reset_idle()

        finally:
            self._busy = False
            self._busy_since = None
