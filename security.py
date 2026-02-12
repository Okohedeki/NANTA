import functools
import logging

from telegram import Update
from telegram.ext import ContextTypes

logger = logging.getLogger(__name__)


def authorized(func):
    """Decorator that restricts handler to allowed chat IDs."""

    @functools.wraps(func)
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE):
        config = context.bot_data["config"]
        chat_id = update.effective_chat.id

        if chat_id not in config.allowed_chat_ids:
            logger.warning("Unauthorized access from chat_id=%d", chat_id)
            await update.message.reply_text(
                f"Unauthorized. Your chat ID: {chat_id}"
            )
            return

        return await func(update, context)

    return wrapper
