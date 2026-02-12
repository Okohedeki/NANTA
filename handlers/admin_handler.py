import logging
import os

from telegram import Update
from telegram.ext import ContextTypes

from security import authorized
from services.claude_runner import (
    get_session,
    is_running,
    reset_session,
)

logger = logging.getLogger(__name__)


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /start - welcome message with chat ID (no auth required)."""
    chat_id = update.effective_chat.id
    await update.message.reply_text(
        f"ClaudePhone Bot\n\n"
        f"Your chat ID: {chat_id}\n\n"
        f"Add this ID to ALLOWED_CHAT_IDS in .env to authorize access.\n"
        f"Then send /help for available commands."
    )


@authorized
async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /help - list all commands."""
    await update.message.reply_text(
        "/claude <prompt> - Send prompt to Claude Code\n"
        "/cl <prompt> - Short alias for /claude\n"
        "/sh <command> - Execute shell command\n"
        "/cancel - Kill running Claude process\n"
        "/status - Show session info\n"
        "/cwd [path] - Get/set working directory\n"
        "/model [name] - Get/set Claude model\n"
        "/newsession - Start fresh Claude session\n"
        "/start - Show your chat ID\n"
        "/help - This message"
    )


@authorized
async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /status - show session info."""
    chat_id = update.effective_chat.id
    config = context.bot_data["config"]
    session = get_session(chat_id, config.default_cwd, config.default_model)

    running = is_running(chat_id)
    cwd = context.bot_data.get("cwd", {}).get(chat_id, session.working_dir)

    await update.message.reply_text(
        f"Session: {session.session_id}\n"
        f"Model: {session.model}\n"
        f"Working dir: {cwd}\n"
        f"Running: {'yes' if running else 'no'}\n"
        f"Total cost: ${session.total_cost_usd:.4f}\n"
        f"Turn: {'first' if session.is_first_turn else 'follow-up'}"
    )


@authorized
async def cwd_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /cwd [path] - get or set working directory."""
    chat_id = update.effective_chat.id
    config = context.bot_data["config"]

    # Ensure cwd dict exists
    if "cwd" not in context.bot_data:
        context.bot_data["cwd"] = {}

    if not context.args:
        current = context.bot_data["cwd"].get(chat_id, config.default_cwd)
        await update.message.reply_text(f"Current directory: {current}")
        return

    new_path = " ".join(context.args)

    if not os.path.isdir(new_path):
        await update.message.reply_text(f"Directory not found: {new_path}")
        return

    new_path = os.path.abspath(new_path)
    context.bot_data["cwd"][chat_id] = new_path

    # Also update Claude session working dir
    session = get_session(chat_id, config.default_cwd, config.default_model)
    session.working_dir = new_path

    await update.message.reply_text(f"Working directory set to: {new_path}")


@authorized
async def model_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /model [name] - get or set Claude model."""
    chat_id = update.effective_chat.id
    config = context.bot_data["config"]
    session = get_session(chat_id, config.default_cwd, config.default_model)

    if not context.args:
        await update.message.reply_text(f"Current model: {session.model}")
        return

    new_model = context.args[0]
    session.model = new_model
    await update.message.reply_text(f"Model set to: {new_model}")


@authorized
async def newsession_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /newsession - start fresh Claude session."""
    chat_id = update.effective_chat.id
    config = context.bot_data["config"]

    # Preserve current cwd
    cwd = context.bot_data.get("cwd", {}).get(chat_id, config.default_cwd)
    session = reset_session(chat_id, cwd, config.default_model)

    await update.message.reply_text(
        f"New session started: {session.session_id}"
    )
