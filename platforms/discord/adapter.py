"""Discord adapter implementing the PlatformContext protocol."""

from __future__ import annotations

import os
import re
from typing import TYPE_CHECKING

import discord

if TYPE_CHECKING:
    from discord.ext.commands import Context as DiscordCmdContext

_URL_RE = re.compile(r"https?://[^\s<>\"']+")


class DiscordMessage:
    """Wraps a Discord message for the platform-agnostic interface."""

    def __init__(self, message: discord.Message):
        self._msg = message

    async def reply(self, text: str) -> DiscordMessage:
        sent = await self._msg.reply(text, mention_author=False)
        return DiscordMessage(sent)

    async def edit(self, text: str) -> None:
        try:
            await self._msg.edit(content=text)
        except Exception:
            pass


class DiscordContext:
    """Wraps discord.ext.commands.Context into PlatformContext."""

    def __init__(self, cmd_ctx: DiscordCmdContext, config, db, cwd_store: dict):
        self._ctx = cmd_ctx
        self._config = config
        self._db = db
        self._cwd_store = cwd_store

    @property
    def user_id(self) -> str:
        return f"discord:{self._ctx.author.id}"

    @property
    def raw_text(self) -> str:
        return self._ctx.message.content or ""

    @property
    def command_args(self) -> list[str]:
        # discord.ext.commands strips the command prefix; the rest is in ctx.message.content
        # We parse args from the raw message after the command
        msg = self._ctx.message.content
        if self._ctx.command:
            # Remove the prefix + command name
            prefix = self._ctx.prefix or ""
            cmd_name = self._ctx.invoked_with or ""
            after = msg[len(prefix) + len(cmd_name):].strip()
            return after.split() if after else []
        return msg.split() if msg else []

    @property
    def message(self) -> DiscordMessage:
        return DiscordMessage(self._ctx.message)

    @property
    def platform_name(self) -> str:
        return "discord"

    @property
    def max_message_length(self) -> int:
        return 2000

    @property
    def edit_interval(self) -> float:
        return 3.0  # Discord is stricter on edit rate limits

    def get_config(self):
        return self._config

    def get_db(self):
        return self._db

    def get_cwd(self) -> str:
        return self._cwd_store.get(str(self._ctx.author.id), self._config.default_cwd)

    def set_cwd(self, path: str) -> None:
        self._cwd_store[str(self._ctx.author.id)] = path

    def extract_urls(self) -> list[str]:
        return _URL_RE.findall(self._ctx.message.content or "")

    async def download_attachment(self, tmp_dir: str) -> tuple[str, str] | None:
        if not self._ctx.message.attachments:
            return None

        attachment = self._ctx.message.attachments[0]
        content_type = attachment.content_type or ""

        if "audio" in content_type:
            source_type = "audio"
        elif "video" in content_type:
            source_type = "video"
        elif attachment.filename and attachment.filename.endswith((".ogg", ".wav", ".mp3", ".m4a", ".flac")):
            source_type = "audio"
        elif attachment.filename and attachment.filename.endswith((".mp4", ".webm", ".mov", ".mkv")):
            source_type = "video"
        else:
            return None

        file_path = os.path.join(tmp_dir, f"{source_type}_{attachment.id}_{attachment.filename}")
        await attachment.save(file_path)
        return file_path, source_type


class DiscordMessageContext:
    """Adapter for on_message events (no command context)."""

    def __init__(self, msg: discord.Message, config, db, cwd_store: dict):
        self._msg = msg
        self._config = config
        self._db = db
        self._cwd_store = cwd_store

    @property
    def user_id(self) -> str:
        return f"discord:{self._msg.author.id}"

    @property
    def raw_text(self) -> str:
        return self._msg.content or ""

    @property
    def command_args(self) -> list[str]:
        return (self._msg.content or "").split()

    @property
    def message(self) -> DiscordMessage:
        return DiscordMessage(self._msg)

    @property
    def platform_name(self) -> str:
        return "discord"

    @property
    def max_message_length(self) -> int:
        return 2000

    @property
    def edit_interval(self) -> float:
        return 3.0

    def get_config(self):
        return self._config

    def get_db(self):
        return self._db

    def get_cwd(self) -> str:
        return self._cwd_store.get(str(self._msg.author.id), self._config.default_cwd)

    def set_cwd(self, path: str) -> None:
        self._cwd_store[str(self._msg.author.id)] = path

    def extract_urls(self) -> list[str]:
        return _URL_RE.findall(self._msg.content or "")

    async def download_attachment(self, tmp_dir: str) -> tuple[str, str] | None:
        if not self._msg.attachments:
            return None

        attachment = self._msg.attachments[0]
        content_type = attachment.content_type or ""

        if "audio" in content_type:
            source_type = "audio"
        elif "video" in content_type:
            source_type = "video"
        elif attachment.filename and attachment.filename.endswith((".ogg", ".wav", ".mp3", ".m4a", ".flac")):
            source_type = "audio"
        elif attachment.filename and attachment.filename.endswith((".mp4", ".webm", ".mov", ".mkv")):
            source_type = "video"
        else:
            return None

        file_path = os.path.join(tmp_dir, f"{source_type}_{attachment.id}_{attachment.filename}")
        await attachment.save(file_path)
        return file_path, source_type
