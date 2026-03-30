"""Discord bot entry point using discord.py."""

import asyncio
import logging
import os
import re

import discord
from discord.ext import commands as dc_commands

from platforms.discord.adapter import DiscordContext, DiscordMessageContext
from core import commands
from services.knowledge_graph import close_db, init_db

logger = logging.getLogger(__name__)

_URL_RE = re.compile(r"https?://[^\s<>\"']+")


def main(config):
    """Start the Discord bot with the given config."""
    logger.info("Discord bot starting with %d allowed IDs", len(config.discord.allowed_ids))

    intents = discord.Intents.default()
    intents.message_content = True

    bot = dc_commands.Bot(command_prefix="!", intents=intents, help_command=None)

    # Shared state
    db = None
    cwd_store: dict[str, str] = {}

    def _ctx(cmd_ctx):
        return DiscordContext(cmd_ctx, config, db, cwd_store)

    def _msg_ctx(msg):
        return DiscordMessageContext(msg, config, db, cwd_store)

    @bot.event
    async def on_ready():
        nonlocal db
        os.makedirs(os.path.dirname(config.kg_db_path), exist_ok=True)
        os.makedirs(os.path.join(os.path.dirname(config.kg_db_path), "tmp"), exist_ok=True)
        db = await init_db(config.kg_db_path)
        logger.info("Discord bot ready as %s", bot.user)

    # ── Commands ─────────────────────────────────────────────

    @bot.command(name="start")
    async def cmd_start(ctx):
        await commands.handle_start(_ctx(ctx))

    @bot.command(name="help")
    async def cmd_help(ctx):
        await commands.handle_help(_ctx(ctx))

    @bot.command(name="status")
    async def cmd_status(ctx):
        await commands.handle_status(_ctx(ctx))

    @bot.command(name="cwd")
    async def cmd_cwd(ctx):
        await commands.handle_cwd(_ctx(ctx))

    @bot.command(name="model")
    async def cmd_model(ctx):
        await commands.handle_model(_ctx(ctx))

    @bot.command(name="newsession")
    async def cmd_newsession(ctx):
        await commands.handle_newsession(_ctx(ctx))

    @bot.command(name="commands")
    async def cmd_commands(ctx):
        await commands.handle_commands(_ctx(ctx))

    @bot.command(name="mcp")
    async def cmd_mcp(ctx):
        await commands.handle_mcp(_ctx(ctx))

    @bot.command(name="restart")
    async def cmd_restart(ctx):
        await commands.handle_restart(_ctx(ctx))

    @bot.command(name="claude", aliases=["cl"])
    async def cmd_claude(ctx):
        await commands.handle_claude(_ctx(ctx))

    @bot.command(name="cancel")
    async def cmd_cancel(ctx):
        await commands.handle_cancel(_ctx(ctx))

    @bot.command(name="sh")
    async def cmd_sh(ctx):
        await commands.handle_shell(_ctx(ctx))

    @bot.command(name="kg")
    async def cmd_kg(ctx):
        await commands.handle_kg(_ctx(ctx))

    @bot.command(name="kgsearch")
    async def cmd_kgsearch(ctx):
        await commands.handle_kgsearch(_ctx(ctx))

    @bot.command(name="kgstats")
    async def cmd_kgstats(ctx):
        await commands.handle_kgstats(_ctx(ctx))

    @bot.command(name="kgrecent")
    async def cmd_kgrecent(ctx):
        await commands.handle_kgrecent(_ctx(ctx))

    # ── Message handlers ─────────────────────────────────────

    @bot.event
    async def on_message(message: discord.Message):
        if message.author.bot:
            return

        # Let commands process first
        await bot.process_commands(message)

        # Skip if it was a command
        ctx = await bot.get_context(message)
        if ctx.valid:
            return

        mc = _msg_ctx(message)

        # Check for media attachments
        if message.attachments:
            attachment = message.attachments[0]
            content_type = attachment.content_type or ""
            is_media = (
                "audio" in content_type
                or "video" in content_type
                or (attachment.filename and attachment.filename.endswith(
                    (".ogg", ".wav", ".mp3", ".m4a", ".flac", ".mp4", ".webm", ".mov", ".mkv")
                ))
            )
            if is_media:
                await commands.handle_media_message(mc)
                return

        text = message.content or ""

        # Check for URLs
        if _URL_RE.search(text):
            await commands.handle_url_message(mc)
            return

        # Default: plain text → Claude
        if text.strip():
            await commands.handle_default_message(mc)

    bot.run(config.discord.token, log_handler=None)
