import logging
import os

from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters

from config import load_config
from handlers.admin_handler import (
    commands_command,
    cwd_command,
    help_command,
    mcp_command,
    model_command,
    newsession_command,
    restart_command,
    start_command,
    status_command,
)
from handlers.claude_handler import cancel_command, claude_command, default_message_handler
from handlers.ingest_handler import (
    kg_command,
    kgrecent_command,
    kgsearch_command,
    kgstats_command,
    media_message_handler,
    url_message_handler,
)
from handlers.shell_handler import sh_command
from services.knowledge_graph import close_db, init_db

logging.basicConfig(
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)


def main():
    config = load_config()
    logger.info("Bot starting with %d allowed chat IDs", len(config.allowed_chat_ids))

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
        .token(config.bot_token)
        .post_init(post_init)
        .post_shutdown(post_shutdown)
        .build()
    )
    app.bot_data["config"] = config

    # Admin commands
    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("status", status_command))
    app.add_handler(CommandHandler("cwd", cwd_command))
    app.add_handler(CommandHandler("model", model_command))
    app.add_handler(CommandHandler("newsession", newsession_command))
    app.add_handler(CommandHandler("commands", commands_command))
    app.add_handler(CommandHandler("mcp", mcp_command))
    app.add_handler(CommandHandler("restart", restart_command))

    # Claude commands
    app.add_handler(CommandHandler("claude", claude_command))
    app.add_handler(CommandHandler("cl", claude_command))
    app.add_handler(CommandHandler("cancel", cancel_command))

    # Shell command
    app.add_handler(CommandHandler("sh", sh_command))

    # Knowledge graph commands
    app.add_handler(CommandHandler("kg", kg_command))
    app.add_handler(CommandHandler("kgsearch", kgsearch_command))
    app.add_handler(CommandHandler("kgstats", kgstats_command))
    app.add_handler(CommandHandler("kgrecent", kgrecent_command))

    # Media handler: voice, audio, video, video notes → transcribe & ingest
    app.add_handler(MessageHandler(
        filters.VOICE | filters.AUDIO | filters.VIDEO | filters.VIDEO_NOTE,
        media_message_handler,
    ))

    # URL handler: text with URLs → extract & ingest (MUST be before default handler)
    app.add_handler(MessageHandler(
        filters.TEXT & ~filters.COMMAND & filters.Entity("url"),
        url_message_handler,
    ))

    # Default: plain text without URLs → Claude
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, default_message_handler))

    # Global error handler
    async def error_handler(update, context):
        logger.error("Unhandled exception: %s", context.error, exc_info=context.error)
        if update and update.effective_message:
            try:
                await update.effective_message.reply_text(
                    f"Error: {context.error}"
                )
            except Exception:
                pass

    app.add_error_handler(error_handler)

    logger.info("Polling started")
    app.run_polling()


if __name__ == "__main__":
    main()
