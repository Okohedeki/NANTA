import logging

from telegram.ext import ApplicationBuilder, CommandHandler

from config import load_config
from handlers.admin_handler import (
    cwd_command,
    help_command,
    model_command,
    newsession_command,
    start_command,
    status_command,
)
from handlers.claude_handler import cancel_command, claude_command
from handlers.shell_handler import sh_command

logging.basicConfig(
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)


def main():
    config = load_config()
    logger.info("Bot starting with %d allowed chat IDs", len(config.allowed_chat_ids))

    app = ApplicationBuilder().token(config.bot_token).build()
    app.bot_data["config"] = config

    # Admin commands
    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("status", status_command))
    app.add_handler(CommandHandler("cwd", cwd_command))
    app.add_handler(CommandHandler("model", model_command))
    app.add_handler(CommandHandler("newsession", newsession_command))

    # Claude commands
    app.add_handler(CommandHandler("claude", claude_command))
    app.add_handler(CommandHandler("cl", claude_command))
    app.add_handler(CommandHandler("cancel", cancel_command))

    # Shell command
    app.add_handler(CommandHandler("sh", sh_command))

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
