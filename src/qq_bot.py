from __future__ import annotations

import asyncio
import logging

import botpy
from botpy import Intents
from botpy.message import C2CMessage, GroupMessage

from config import BotConfig
from sdk_session import SDKSession
from output_processor import chunk, strip_ansi

log = logging.getLogger(__name__)


def _mask(uid: str) -> str:
    if len(uid) <= 4:
        return uid
    return uid[:2] + "***" + uid[-2:]


HELP_TEXT = (
    "命令列表：\n"
    "/start  — 启动 Claude Code 会话\n"
    "/stop   — 停止会话\n"
    "/restart — 重启会话（清除上下文）\n"
    "/cancel — 取消当前正在处理的消息\n"
    "/status — 查看会话状态\n"
    "/help   — 显示此消息\n\n"
    "其他消息将转发给 Claude Code。"
)


class QQBotClient(botpy.Client):
    """QQ Bot client wrapping Claude Agent SDK session."""

    def __init__(self, cfg: BotConfig, **kwargs):
        super().__init__(**kwargs)
        self.cfg = cfg
        self.session = SDKSession(cfg.project_path, cfg.model, cfg.api_url, cfg.api_key)
        self._heartbeat_task: asyncio.Task | None = None

    async def on_ready(self):
        log.info("QQ Bot [%s] ready", self.cfg.project_name)
        self._heartbeat_task = asyncio.create_task(self._heartbeat_loop())

    def _allowed_c2c(self, message: C2CMessage) -> bool:
        return message.author.user_openid == self.cfg.allowed_qq_openid

    def _allowed_group(self, message: GroupMessage) -> bool:
        return message.group_openid == self.cfg.allowed_qq_group_openid

    async def _send_text(self, message, text: str):
        """Send text message, splitting if too long."""
        for part in chunk(text, 2000):
            await message.reply(content=part)

    async def on_c2c_message_create(self, message: C2CMessage):
        """Handle C2C (private) messages."""
        if not self._allowed_c2c(message):
            return
        await self._handle_command(message, message.author.user_openid)

    async def on_group_at_message_create(self, message: GroupMessage):
        """Handle group @ messages."""
        if not self._allowed_group(message):
            return
        # Strip @bot mention from content
        content = message.content.strip()
        await self._handle_command(message, message.group_openid)

    async def _handle_command(self, message, user_id: str):
        content = message.content.strip()

        if content == "/start":
            if self.session.is_running:
                await self._send_text(message, "会话已在运行中。")
                return
            self.session.start()
            log.info("[%s] session started by %s", self.cfg.project_name, _mask(user_id))
            await self._send_text(
                message,
                f"就绪。\n项目: {self.cfg.project_name}\n模型: {self.cfg.model}"
            )

        elif content == "/stop":
            if not self.session.is_running:
                await self._send_text(message, "会话未在运行。")
                return
            self.session.stop()
            log.info("[%s] session stopped by %s", self.cfg.project_name, _mask(user_id))
            await self._send_text(message, "会话已停止。")

        elif content == "/restart":
            self.session.restart()
            await self._send_text(message, "会话已重启。")

        elif content == "/cancel":
            if not self.session.is_busy:
                await self._send_text(message, "当前没有正在处理的消息。")
                return
            self.session.cancel()
            log.info("[%s] message cancelled by %s", self.cfg.project_name, _mask(user_id))
            await self._send_text(message, "已取消当前消息。")

        elif content == "/status":
            if not self.session.is_running:
                text = f"已停止 | {self.cfg.project_name}"
            elif self.session.is_busy:
                text = f"处理中 ({self.session.busy_elapsed}s) | {self.cfg.project_name} | 运行时间: {self.session.uptime}"
            else:
                text = f"空闲 | {self.cfg.project_name} | 运行时间: {self.session.uptime}"
            await self._send_text(message, text)

        elif content == "/help":
            await self._send_text(message, HELP_TEXT)

        else:
            await self._handle_message(message, content)

    async def _handle_message(self, message, text: str):
        if not self.session.is_running:
            await self._send_text(message, "会话未运行，请先发送 /start。")
            return
        if self.session.is_busy:
            await self._send_text(
                message,
                f"正在处理中 ({self.session.busy_elapsed}s)。发送 /cancel 取消。"
            )
            return

        try:
            stream = await self.session.send_message(text)
        except RuntimeError as e:
            await self._send_text(message, f"错误: {e}")
            return

        sent = 0
        try:
            async for raw in stream:
                for part in chunk(strip_ansi(raw), 2000):
                    await message.reply(content=part)
                    sent += 1
        except RuntimeError as e:
            await self._send_text(message, f"错误: {e}")
            return
        except Exception as e:
            log.exception("stream failed")
            self.session.stop()
            await self._send_text(message, f"错误: {e}\n会话已停止，请发送 /start 重启。")
            return

        log.info("[%s] reply %d message(s)", self.cfg.project_name, sent)
        if sent == 0 and not self.session.was_cancelled:
            await self._send_text(message, "（无输出）")

    async def _heartbeat_loop(self):
        while True:
            await asyncio.sleep(60)
            if self.session.is_busy:
                status = f"busy ({self.session.busy_elapsed}s)"
            elif self.session.is_running:
                status = "idle"
            else:
                status = "stopped"
            log.info("[heartbeat] %s | %s | uptime=%s",
                     self.cfg.project_name, status, self.session.uptime)


class QQBot:
    """Wrapper that manages the QQ Bot lifecycle."""

    def __init__(self, cfg: BotConfig) -> None:
        self.cfg = cfg
        intents = Intents(public_messages=True)
        self.client = QQBotClient(
            cfg=cfg,
            intents=intents,
            is_sandbox=False,
            log_level=logging.WARNING,
            bot_log=False,
            ext_handlers=False,
        )

    async def start(self):
        log.info("Starting QQ Bot for project: %s", self.cfg.project_name)
        asyncio.ensure_future(self.client.start(self.cfg.qq_app_id, self.cfg.qq_app_secret))

    async def stop(self):
        if self.client._heartbeat_task and not self.client._heartbeat_task.done():
            self.client._heartbeat_task.cancel()
        if self.client.session.is_running:
            self.client.session.stop()
        await self.client.close()
        log.info("QQ Bot stopped for project: %s", self.cfg.project_name)
