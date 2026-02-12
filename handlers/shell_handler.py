import logging

from telegram import Update
from telegram.ext import ContextTypes

from security import authorized
from services.shell_runner import run_shell
from services.output_formatter import chunk_message, format_shell_output

logger = logging.getLogger(__name__)


@authorized
async def sh_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /sh <command> - execute a shell command."""
    if not context.args:
        await update.message.reply_text("Usage: /sh <command>")
        return

    command = " ".join(context.args)
    config = context.bot_data["config"]
    cwd = context.bot_data.get("cwd", {}).get(
        update.effective_chat.id, config.default_cwd
    )

    msg = await update.message.reply_text(f"Running: `{command}`", parse_mode="Markdown")

    return_code, output = await run_shell(command, cwd, config.shell_timeout)
    result = format_shell_output(return_code, output)

    chunks = chunk_message(result)

    # Edit first message, send rest as new messages
    await msg.edit_text(chunks[0])
    for chunk in chunks[1:]:
        await update.message.reply_text(chunk)
