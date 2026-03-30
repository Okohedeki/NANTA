"""Telegram bot entry point using python-telegram-bot."""

import logging
import os

from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters

from platforms.telegram.adapter import TelegramContext
from core import commands
from services.knowledge_graph import close_db, init_db

logger = logging.getLogger(__name__)


def _wrap(handler_fn):
    """Create a Telegram handler that wraps Update+Context into TelegramContext."""
    async def wrapper(update, context):
        ctx = TelegramContext(update, context)
        await handler_fn(ctx)
    return wrapper


def main(config):
    """Start the Telegram bot with the given config."""
    logger.info("Telegram bot starting with %d allowed IDs", len(config.telegram.allowed_ids))

    # Ensure data directories exist
    os.makedirs(os.path.dirname(config.kg_db_path), exist_ok=True)
    os.makedirs(os.path.join(os.path.dirname(config.kg_db_path), "tmp"), exist_ok=True)

    async def post_init(application):
        application.bot_data["kg_db"] = await init_db(config.kg_db_path)

    async def post_shutdown(application):
        db = application.bot_data.get("kg_db")
        if db:
            await close_db(db)

    app = (
        ApplicationBuilder()
        .token(config.telegram.token)
        .post_init(post_init)
        .post_shutdown(post_shutdown)
        .build()
    )
    app.bot_data["config"] = config

    # Admin commands
    app.add_handler(CommandHandler("start", _wrap(commands.handle_start)))
    app.add_handler(CommandHandler("help", _wrap(commands.handle_help)))
    app.add_handler(CommandHandler("status", _wrap(commands.handle_status)))
    app.add_handler(CommandHandler("cwd", _wrap(commands.handle_cwd)))
    app.add_handler(CommandHandler("model", _wrap(commands.handle_model)))
    app.add_handler(CommandHandler("newsession", _wrap(commands.handle_newsession)))
    app.add_handler(CommandHandler("commands", _wrap(commands.handle_commands)))
    app.add_handler(CommandHandler("mcp", _wrap(commands.handle_mcp)))
    app.add_handler(CommandHandler("restart", _wrap(commands.handle_restart)))

    # Claude commands
    app.add_handler(CommandHandler("claude", _wrap(commands.handle_claude)))
    app.add_handler(CommandHandler("cl", _wrap(commands.handle_claude)))
    app.add_handler(CommandHandler("cancel", _wrap(commands.handle_cancel)))

    # Shell command
    app.add_handler(CommandHandler("sh", _wrap(commands.handle_shell)))

    # Knowledge graph commands
    app.add_handler(CommandHandler("kg", _wrap(commands.handle_kg)))
    app.add_handler(CommandHandler("kgsearch", _wrap(commands.handle_kgsearch)))
    app.add_handler(CommandHandler("kgstats", _wrap(commands.handle_kgstats)))
    app.add_handler(CommandHandler("kgrecent", _wrap(commands.handle_kgrecent)))

    # Media handler: voice, audio, video, video notes → transcribe & ingest
    app.add_handler(MessageHandler(
        filters.VOICE | filters.AUDIO | filters.VIDEO | filters.VIDEO_NOTE,
        _wrap(commands.handle_media_message),
    ))

    # URL handler: text with URLs → extract & ingest (MUST be before default handler)
    app.add_handler(MessageHandler(
        filters.TEXT & ~filters.COMMAND & filters.Entity("url"),
        _wrap(commands.handle_url_message),
    ))

    # Default: plain text without URLs → Claude
    app.add_handler(MessageHandler(
        filters.TEXT & ~filters.COMMAND,
        _wrap(commands.handle_default_message),
    ))

    # Global error handler
    async def error_handler(update, context):
        logger.error("Unhandled exception: %s", context.error, exc_info=context.error)
        if update and update.effective_message:
            try:
                await update.effective_message.reply_text(f"Error: {context.error}")
            except Exception:
                pass

    app.add_error_handler(error_handler)

    logger.info("Telegram polling started")
    app.run_polling()
