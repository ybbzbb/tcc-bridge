import logging

from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

import config
from cc_session import CCSession, State
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
    def __init__(self) -> None:
        self.session = CCSession(config.PROJECT_PATH, config.CC_MODEL)
        self.app = Application.builder().token(config.BOT_TOKEN).build()
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
        return update.effective_user.id == config.ALLOWED_USER_ID

    async def _cmd_start(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not self._allowed(update):
            return
        if self.session.state == State.RUNNING:
            await update.message.reply_text("⚠️ Session is already running.")
            return
        await update.message.reply_text("🚀 Starting Claude Code...")
        try:
            await self.session.start()
            await update.message.reply_text(
                f"✅ Ready.\nProject: {config.PROJECT_NAME}\nModel: {config.CC_MODEL}"
            )
        except Exception as e:
            log.exception("start failed")
            await update.message.reply_text(f"❌ Failed to start: {e}")

    async def _cmd_stop(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not self._allowed(update):
            return
        if self.session.state == State.STOPPED:
            await update.message.reply_text("⚠️ Session is not running.")
            return
        await self.session.stop()
        await update.message.reply_text("🔴 Session stopped.")

    async def _cmd_restart(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not self._allowed(update):
            return
        await update.message.reply_text("🔄 Restarting...")
        try:
            await self.session.restart()
            await update.message.reply_text("✅ Session restarted.")
        except Exception as e:
            log.exception("restart failed")
            await update.message.reply_text(f"❌ Restart failed: {e}")

    async def _cmd_status(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not self._allowed(update):
            return
        s = self.session
        if s.state == State.STOPPED:
            text = f"🔴 Stopped | {config.PROJECT_NAME}"
        elif s.is_busy:
            text = f"⏳ Busy | {config.PROJECT_NAME} | Uptime: {s.uptime}"
        else:
            text = f"✅ Idle | {config.PROJECT_NAME} | Uptime: {s.uptime}"
        await update.message.reply_text(text)

    async def _cmd_help(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not self._allowed(update):
            return
        await update.message.reply_text(HELP_TEXT)

    async def _on_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not self._allowed(update):
            return
        if self.session.state != State.RUNNING:
            await update.message.reply_text("🔴 Session not running. Send /start first.")
            return
        if self.session.is_busy:
            await update.message.reply_text("⏳ Claude Code is busy. Wait for it to finish.")
            return

        try:
            response = await self.session.send_message(update.message.text)
        except RuntimeError as e:
            await update.message.reply_text(f"❌ {e}")
            return
        except Exception as e:
            log.exception("send_message failed")
            await self.session.stop()
            await update.message.reply_text(
                f"❌ Error: {e}\nSession stopped. Use /start to restart."
            )
            return

        parts = chunk(strip_ansi(response), config.CHUNK_SIZE)
        if not parts:
            await update.message.reply_text("_(no output)_")
            return
        for part in parts:
            await context.bot.send_message(config.ALLOWED_USER_ID, part)

    def run(self) -> None:
        self.app.run_polling(allowed_updates=Update.ALL_TYPES)
