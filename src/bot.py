from __future__ import annotations

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
from cc_session import CCSession
from output_processor import chunk, strip_ansi

log = logging.getLogger(__name__)

HELP_TEXT = (
    "Commands:\n"
    "/start   — Start Claude Code session\n"
    "/stop    — Stop session\n"
    "/restart — Restart session (clears context)\n"
    "/status  — Show session status\n"
    "/help    — Show this message\n\n"
    "Any other message is forwarded to Claude Code."
)


class TelegramBot:
    def __init__(self, cfg: BotConfig) -> None:
        self.cfg = cfg
        self.session = CCSession(cfg.project_path, cfg.model, cfg.api_url, cfg.api_key)
        self.app = Application.builder().token(cfg.token).build()
        self._register_handlers()

    def _register_handlers(self) -> None:
        self.app.add_handler(CommandHandler("start", self._cmd_start))
        self.app.add_handler(CommandHandler("stop", self._cmd_stop))
        self.app.add_handler(CommandHandler("restart", self._cmd_restart))
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
        log.info("[%s] session started by user %s", self.cfg.project_name, update.effective_user.id)
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
        log.info("[%s] session stopped by user %s", self.cfg.project_name, update.effective_user.id)
        await update.message.reply_text("🔴 Session stopped.")

    async def _cmd_restart(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not self._allowed(update):
            return
        self.session.restart()
        await update.message.reply_text("✅ Session restarted.")

    async def _cmd_status(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not self._allowed(update):
            return
        if not self.session.is_running:
            text = f"🔴 Stopped | {self.cfg.project_name}"
        elif self.session.is_busy:
            text = f"⏳ Busy | {self.cfg.project_name} | Uptime: {self.session.uptime}"
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
            await update.message.reply_text("⏳ Claude Code is busy. Wait for it to finish.")
            return

        try:
            stream = await self.session.send_message(update.message.text)
        except RuntimeError as e:
            await update.message.reply_text(f"❌ {e}")
            return

        sent = 0
        try:
            async for raw in stream:
                for part in chunk(strip_ansi(raw), self.cfg.chunk_size):
                    await context.bot.send_message(self.cfg.allowed_user_id, part)
                    sent += 1
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
        if sent == 0:
            await update.message.reply_text("_(no output)_")

    async def start(self) -> None:
        await self.app.initialize()
        await self.app.start()
        await self.app.updater.start_polling(allowed_updates=Update.ALL_TYPES)
        log.info("Bot started for project: %s", self.cfg.project_name)

    async def stop(self) -> None:
        await self.app.updater.stop()
        await self.app.stop()
        await self.app.shutdown()
        if self.session.is_running:
            self.session.stop()
        log.info("Bot stopped for project: %s", self.cfg.project_name)
