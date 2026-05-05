from __future__ import annotations

import asyncio
import logging
import os
import time

log = logging.getLogger(__name__)

MAX_RESPONSE = 600.0  # 10 min hard cap


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

    async def send_message(self, text: str) -> str:
        if not self.is_running:
            raise RuntimeError("Session is not running")
        if self._busy:
            raise RuntimeError("Session is busy")

        self._busy = True
        try:
            proc = await asyncio.create_subprocess_exec(
                "claude", "--print", "--continue",
                "--dangerously-skip-permissions",
                "--model", self.model,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
                cwd=self.project_path,
                env=self._build_env(),
            )
            try:
                stdout, _ = await asyncio.wait_for(
                    proc.communicate(text.encode()),
                    timeout=MAX_RESPONSE,
                )
            except asyncio.TimeoutError:
                proc.kill()
                raise RuntimeError("CC response timed out (10 min)")

            output = stdout.decode("utf-8", errors="replace").strip()
            if proc.returncode != 0:
                raise RuntimeError(
                    f"CC exited with code {proc.returncode}.\n{output[-500:] or '(no output)'}"
                )
            return output
        finally:
            self._busy = False
