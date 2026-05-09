from __future__ import annotations

import asyncio
import logging
import time
from typing import AsyncIterator

from claude_agent_sdk import (
    AssistantMessage,
    ClaudeAgentOptions,
    ClaudeSDKClient,
    TextBlock,
)

log = logging.getLogger(__name__)

MAX_RESPONSE = 600.0     # 10 min hard cap per message
IDLE_SHUTDOWN = 30 * 60  # 30 min no messages → auto-stop


class SDKSession:
    """Claude Agent SDK backend — persistent multi-turn session."""

    def __init__(self, project_path: str, model: str,
                 api_url: str | None = None, api_key: str | None = None):
        self.project_path = project_path
        self.model = model
        self.api_url = api_url
        self.api_key = api_key
        self._client: ClaudeSDKClient | None = None
        self._busy = False
        self._busy_since: float | None = None
        self._cancelled = False
        self._started_at: float | None = None
        self._idle_task: asyncio.Task | None = None
        self._current_task: asyncio.Task | None = None

    def _build_options(self) -> ClaudeAgentOptions:
        env = {}
        if self.api_url:
            env["ANTHROPIC_BASE_URL"] = self.api_url
        if self.api_key:
            env["ANTHROPIC_AUTH_TOKEN"] = self.api_key
        opts = ClaudeAgentOptions(
            cwd=self.project_path,
            model=self.model,
            allowed_tools=["Read", "Write", "Edit", "MultiEdit",
                           "Bash", "Glob", "Grep", "WebFetch", "WebSearch"],
            permission_mode="acceptEdits",
            max_turns=200,
            env=env or None,
        )
        return opts

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
        if self._current_task and not self._current_task.done():
            self._current_task.cancel()

    def start(self) -> None:
        self._started_at = time.time()
        self._reset_idle()
        log.info("[%s] SDK session started", self.project_path)

    def stop(self) -> None:
        self._started_at = None
        self._busy = False
        self._busy_since = None
        self._cancel_idle()
        if self._current_task and not self._current_task.done():
            self._current_task.cancel()
        self._current_task = None
        # Client will be recreated on next message
        self._client = None
        log.info("[%s] SDK session stopped", self.project_path)

    def restart(self) -> None:
        self.stop()
        self.start()

    # -- idle monitor --

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
            log.info("[%s] Idle 30 min, auto-stopping SDK session", self.project_path)
            self.stop()
        except asyncio.CancelledError:
            pass

    # -- message handling --

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
            log.info(">>> [%s] (SDK) %s", self.project_path, text[:200])

            options = self._build_options()

            # Use ClaudeSDKClient for multi-turn persistent session
            if self._client is None:
                self._client = ClaudeSDKClient(options=options)
                await self._client.__aenter__()

            await self._client.query(text)

            total_chars = 0
            loop = asyncio.get_running_loop()
            deadline = loop.time() + MAX_RESPONSE
            start_time = loop.time()
            last_heartbeat = start_time

            async for message in self._client.receive_response():
                if self._cancelled:
                    break

                remaining = deadline - loop.time()
                if remaining <= 0:
                    raise RuntimeError("Response timed out (10 min)")

                if isinstance(message, AssistantMessage):
                    for block in message.content:
                        if isinstance(block, TextBlock) and block.text:
                            total_chars += len(block.text)
                            yield block.text

                now = loop.time()
                if now - last_heartbeat >= 10:
                    log.info("... SDK running (%.0fs elapsed)", now - start_time)
                    last_heartbeat = now

            if not self._cancelled:
                log.info("<<< [%s] (SDK) done, %d chars received",
                         self.project_path, total_chars)
                self._reset_idle()

        except asyncio.CancelledError:
            log.info("[%s] SDK message cancelled", self.project_path)
        except Exception:
            log.exception("[%s] SDK stream failed", self.project_path)
            raise
        finally:
            self._busy = False
            self._busy_since = None
