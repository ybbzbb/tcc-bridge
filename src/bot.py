from __future__ import annotations

import asyncio
import logging

from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from config import BotConfig
from sdk_session import SDKSession
from output_processor import chunk, strip_ansi

log = logging.getLogger(__name__)


def _mask(uid: int) -> str:
    s = str(uid)
    return s[:2] + "***" + s[-2:]


HELP_TEXT = (
    "Commands:\n"
    "/start         — Start Claude Code session\n"
    "/stop          — Stop session\n"
    "/restart       — Restart session (clears context)\n"
    "/close_message — Cancel the current in-progress message\n"
    "/status        — Show session status\n"
    "/help          — Show this message\n\n"
    "Any other message is forwarded to Claude Code."
)


class TelegramBot:
    def __init__(self, cfg: BotConfig) -> None:
        self.cfg = cfg
        self.session = SDKSession(cfg.project_path, cfg.model, cfg.api_url, cfg.api_key)
        builder = Application.builder().token(cfg.token)
        if cfg.telegram_api_url:
            base = cfg.telegram_api_url.rstrip("/")
            builder = builder.base_url(f"{base}/bot").base_file_url(f"{base}/file/bot")
        httpx_kwargs = {}
        if cfg.telegram_api_key:
            httpx_kwargs["headers"] = {"X-TCC-Key": cfg.telegram_api_key}
        if cfg.telegram_proxy:
            import httpx
            httpx_kwargs["proxy"] = cfg.telegram_proxy
        if httpx_kwargs:
            from telegram.request import HTTPXRequest
            request = HTTPXRequest(httpx_kwargs=httpx_kwargs or None)
            builder = builder.request(request)
            builder = builder.get_updates_request(HTTPXRequest(httpx_kwargs=httpx_kwargs or None))
        self.app = builder.build()
        self._heartbeat_task: asyncio.Task | None = None
        self._register_handlers()

    def _register_handlers(self) -> None:
        self.app.add_handler(CommandHandler("start", self._cmd_start))
        self.app.add_handler(CommandHandler("stop", self._cmd_stop))
        self.app.add_handler(CommandHandler("restart", self._cmd_restart))
        self.app.add_handler(CommandHandler("close_message", self._cmd_close_message))
        self.app.add_handler(CommandHandler("status", self._cmd_status))
        self.app.add_handler(CommandHandler("help", self._cmd_help))
        self.app.add_handler(
            MessageHandler(filters.TEXT & ~filters.COMMAND, self._on_message)
        )

    def _allowed(self, update: Update) -> bool:
        return update.effective_user.id == self.cfg.allowed_user_id

    async def _cmd_start(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not self._allowed(update):
            return
        if self.session.is_running:
            await update.message.reply_text("⚠️ Session is already running.")
            return
        self.session.start()
        log.info("[%s] session started by user %s", self.cfg.project_name, _mask(update.effective_user.id))
        await update.message.reply_text(
            f"✅ Ready.\nProject: {self.cfg.project_name}\nModel: {self.cfg.model}"
        )

    async def _cmd_stop(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not self._allowed(update):
            return
        if not self.session.is_running:
            await update.message.reply_text("⚠️ Session is not running.")
            return
        self.session.stop()
        log.info("[%s] session stopped by user %s", self.cfg.project_name, _mask(update.effective_user.id))
        await update.message.reply_text("🔴 Session stopped.")

    async def _cmd_restart(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not self._allowed(update):
            return
        self.session.restart()
        await update.message.reply_text("✅ Session restarted.")

    async def _cmd_close_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not self._allowed(update):
            return
        if not self.session.is_busy:
            await update.message.reply_text("⚠️ No message in progress.")
            return
        self.session.cancel()
        log.info("[%s] message cancelled by user %s", self.cfg.project_name, _mask(update.effective_user.id))
        await update.message.reply_text("🚫 Message cancelled.")

    async def _cmd_status(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not self._allowed(update):
            return
        if not self.session.is_running:
            text = f"🔴 Stopped | {self.cfg.project_name}"
        elif self.session.is_busy:
            text = f"⏳ Busy ({self.session.busy_elapsed}s) | {self.cfg.project_name} | Uptime: {self.session.uptime}"
        else:
            text = f"✅ Idle | {self.cfg.project_name} | Uptime: {self.session.uptime}"
        await update.message.reply_text(text)

    async def _cmd_help(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not self._allowed(update):
            return
        await update.message.reply_text(HELP_TEXT)

    async def _on_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not self._allowed(update):
            return
        if not self.session.is_running:
            await update.message.reply_text("🔴 Session not running. Send /start first.")
            return
        if self.session.is_busy:
            await update.message.reply_text(
                f"⏳ Busy ({self.session.busy_elapsed}s elapsed). "
                f"Use /close_message to cancel."
            )
            return

        try:
            stream = await self.session.send_message(update.message.text)
        except RuntimeError as e:
            await update.message.reply_text(f"❌ {e}")
            return

        await context.bot.send_chat_action(self.cfg.allowed_user_id, "typing")

        sent = 0
        try:
            async for raw in stream:
                for part in chunk(strip_ansi(raw), self.cfg.chunk_size):
                    await context.bot.send_message(self.cfg.allowed_user_id, part)
                    sent += 1
                    # Refresh typing indicator every ~20 messages
                    if sent % 20 == 0:
                        await context.bot.send_chat_action(self.cfg.allowed_user_id, "typing")
        except RuntimeError as e:
            await update.message.reply_text(f"❌ {e}")
            return
        except Exception as e:
            log.exception("stream failed")
            self.session.stop()
            await update.message.reply_text(
                f"❌ Error: {e}\nSession stopped. Use /start to restart."
            )
            return

        log.info("[%s] reply %d message(s)", self.cfg.project_name, sent)
        if sent == 0 and not self.session.was_cancelled:
            await update.message.reply_text("_(no output)_")

    async def _heartbeat_loop(self) -> None:
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

    async def start(self) -> None:
        await self.app.initialize()
        await self.app.start()
        await self.app.updater.start_polling(allowed_updates=Update.ALL_TYPES)
        self._heartbeat_task = asyncio.create_task(self._heartbeat_loop())
        log.info("Bot started for project: %s", self.cfg.project_name)

    async def stop(self) -> None:
        if self._heartbeat_task and not self._heartbeat_task.done():
            self._heartbeat_task.cancel()
        await self.app.updater.stop()
        await self.app.stop()
        await self.app.shutdown()
        if self.session.is_running:
            self.session.stop()
        log.info("Bot stopped for project: %s", self.cfg.project_name)
