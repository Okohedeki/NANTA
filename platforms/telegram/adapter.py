"""Telegram adapter implementing the PlatformContext protocol."""

from __future__ import annotations

import os
import re

from telegram import Update
from telegram.ext import ContextTypes


class TelegramMessage:
    """Wraps a Telegram message for the platform-agnostic interface."""

    def __init__(self, message):
        self._msg = message

    async def reply(self, text: str) -> TelegramMessage:
        sent = await self._msg.reply_text(text)
        return TelegramMessage(sent)

    async def edit(self, text: str) -> None:
        try:
            await self._msg.edit_text(text)
        except Exception:
            pass  # Telegram may reject identical content or rate-limit


class TelegramContext:
    """Wraps Telegram Update + ContextTypes into PlatformContext."""

    def __init__(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        self._update = update
        self._context = context

    @property
    def user_id(self) -> str:
        return f"telegram:{self._update.effective_chat.id}"

    @property
    def raw_text(self) -> str:
        return self._update.message.text or ""

    @property
    def command_args(self) -> list[str]:
        return list(self._context.args or [])

    @property
    def message(self) -> TelegramMessage:
        return TelegramMessage(self._update.message)

    @property
    def platform_name(self) -> str:
        return "telegram"

    @property
    def max_message_length(self) -> int:
        return 4096

    @property
    def edit_interval(self) -> float:
        return 2.0

    def get_config(self):
        return self._context.bot_data["config"]

    def get_db(self):
        return self._context.bot_data["kg_db"]

    def get_cwd(self) -> str:
        config = self.get_config()
        chat_id = self._update.effective_chat.id
        return self._context.bot_data.get("cwd", {}).get(chat_id, config.default_cwd)

    def set_cwd(self, path: str) -> None:
        if "cwd" not in self._context.bot_data:
            self._context.bot_data["cwd"] = {}
        self._context.bot_data["cwd"][self._update.effective_chat.id] = path

    def extract_urls(self) -> list[str]:
        message = self._update.message
        urls = []
        if not message.entities:
            return urls
        for entity in message.entities:
            if entity.type == "url":
                urls.append(message.parse_entity(entity))
            elif entity.type == "text_link":
                urls.append(entity.url)
        return urls

    async def download_attachment(self, tmp_dir: str) -> tuple[str, str] | None:
        message = self._update.message

        if message.voice:
            media = message.voice
            source_type = "voice"
        elif message.audio:
            media = message.audio
            source_type = "audio"
        elif message.video:
            media = message.video
            source_type = "video"
        elif message.video_note:
            media = message.video_note
            source_type = "video"
        else:
            return None

        file_path = os.path.join(tmp_dir, f"{source_type}_{media.file_unique_id}")
        tg_file = await media.get_file()
        await tg_file.download_to_drive(file_path)
        return file_path, source_type
