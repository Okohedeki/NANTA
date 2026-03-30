import asyncio
import logging
import time

from telegram import Update
from telegram.ext import ContextTypes

from security import authorized
from services.claude_runner import (
    cancel_claude,
    is_running,
    run_claude_streaming,
)
from services.output_formatter import chunk_message

logger = logging.getLogger(__name__)

# Rate limit: edit message at most every 2 seconds
EDIT_INTERVAL = 2.0


@authorized
async def claude_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /claude <prompt> and /cl <prompt>."""
    if not context.args:
        await update.message.reply_text("Usage: /claude <prompt>")
        return

    chat_id = update.effective_chat.id
    prompt = " ".join(context.args)
    config = context.bot_data["config"]

    if is_running(chat_id):
        await update.message.reply_text(
            "Claude is already running. Use /cancel to stop it."
        )
        return

    status_msg = await update.message.reply_text("Thinking...")

    accumulated = ""
    last_edit_time = 0.0
    finished = False
    final_cost = 0.0

    async def on_text_delta(text: str):
        nonlocal accumulated, last_edit_time
        accumulated += text

        now = time.monotonic()
        if now - last_edit_time >= EDIT_INTERVAL:
            last_edit_time = now
            # Show latest ~3500 chars to stay under limit
            preview = accumulated[-3500:] if len(accumulated) > 3500 else accumulated
            if preview.strip():
                try:
                    await status_msg.edit_text(preview)
                except Exception:
                    pass  # Telegram rate limit or identical content

    async def on_result(full_text: str, cost_usd: float):
        nonlocal finished, final_cost, accumulated
        finished = True
        final_cost = cost_usd
        if full_text:
            accumulated = full_text

    try:
        text, cost = await asyncio.wait_for(
            run_claude_streaming(
                chat_id, prompt, config,
                on_text_delta=on_text_delta,
                on_result=on_result,
            ),
            timeout=config.claude_timeout,
        )
    except asyncio.TimeoutError:
        await cancel_claude(chat_id)
        await status_msg.edit_text(
            f"Claude timed out after {config.claude_timeout}s. Process killed."
        )
        return
    except RuntimeError as e:
        await status_msg.edit_text(str(e))
        return
    except Exception:
        logger.exception("Claude command failed")
        await status_msg.edit_text("Claude encountered an error.")
        return

    if not accumulated:
        accumulated = text or "(no output)"
    cost = final_cost or cost

    # Append cost footer
    footer = f"\n\n[cost: ${cost:.4f}]"
    result_text = accumulated.rstrip() + footer

    chunks = chunk_message(result_text)

    try:
        await status_msg.edit_text(chunks[0])
    except Exception:
        pass

    for chunk in chunks[1:]:
        await update.message.reply_text(chunk)


@authorized
async def default_message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle plain text messages as Claude prompts."""
    chat_id = update.effective_chat.id
    prompt = update.message.text
    config = context.bot_data["config"]

    if is_running(chat_id):
        await update.message.reply_text(
            "Claude is already running. Use /cancel to stop it."
        )
        return

    status_msg = await update.message.reply_text("Thinking...")

    accumulated = ""
    last_edit_time = 0.0
    finished = False
    final_cost = 0.0

    async def on_text_delta(text: str):
        nonlocal accumulated, last_edit_time
        accumulated += text

        now = time.monotonic()
        if now - last_edit_time >= EDIT_INTERVAL:
            last_edit_time = now
            preview = accumulated[-3500:] if len(accumulated) > 3500 else accumulated
            if preview.strip():
                try:
                    await status_msg.edit_text(preview)
                except Exception:
                    pass

    async def on_result(full_text: str, cost_usd: float):
        nonlocal finished, final_cost, accumulated
        finished = True
        final_cost = cost_usd
        if full_text:
            accumulated = full_text

    try:
        text, cost = await asyncio.wait_for(
            run_claude_streaming(
                chat_id, prompt, config,
                on_text_delta=on_text_delta,
                on_result=on_result,
            ),
            timeout=config.claude_timeout,
        )
    except asyncio.TimeoutError:
        await cancel_claude(chat_id)
        await status_msg.edit_text(
            f"Claude timed out after {config.claude_timeout}s. Process killed."
        )
        return
    except RuntimeError as e:
        await status_msg.edit_text(str(e))
        return
    except Exception:
        logger.exception("Claude command failed")
        await status_msg.edit_text("Claude encountered an error.")
        return

    if not accumulated:
        accumulated = text or "(no output)"
    cost = final_cost or cost

    footer = f"\n\n[cost: ${cost:.4f}]"
    result_text = accumulated.rstrip() + footer

    chunks = chunk_message(result_text)

    try:
        await status_msg.edit_text(chunks[0])
    except Exception:
        pass

    for chunk in chunks[1:]:
        await update.message.reply_text(chunk)


@authorized
async def cancel_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /cancel - kill running Claude process."""
    chat_id = update.effective_chat.id
    killed = await cancel_claude(chat_id)

    if killed:
        await update.message.reply_text("Claude process cancelled.")
    else:
        await update.message.reply_text("No Claude process is running.")
