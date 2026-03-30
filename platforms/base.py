"""Platform adapter protocol for multi-platform bot support."""

from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class PlatformMessage(Protocol):
    """A sent message that can be edited or replied to."""

    async def reply(self, text: str) -> PlatformMessage: ...
    async def edit(self, text: str) -> None: ...


@runtime_checkable
class PlatformContext(Protocol):
    """Context for an incoming command or message."""

    @property
    def user_id(self) -> str:
        """Platform-qualified ID, e.g. 'telegram:123' or 'discord:456'."""
        ...

    @property
    def raw_text(self) -> str:
        """Full message text."""
        ...

    @property
    def command_args(self) -> list[str]:
        """Arguments after the command keyword."""
        ...

    @property
    def message(self) -> PlatformMessage:
        """The triggering message (can be replied to)."""
        ...

    @property
    def platform_name(self) -> str:
        """'telegram' | 'discord'"""
        ...

    @property
    def max_message_length(self) -> int:
        """Max chars per message (4096 for Telegram, 2000 for Discord)."""
        ...

    @property
    def edit_interval(self) -> float:
        """Minimum seconds between message edits (rate-limit safe)."""
        ...

    def get_config(self):
        """Return the shared Config object."""
        ...

    def get_db(self):
        """Return the knowledge graph DB connection."""
        ...

    def get_cwd(self) -> str:
        """Return the current working directory for this user."""
        ...

    def set_cwd(self, path: str) -> None:
        """Set the working directory for this user."""
        ...

    def extract_urls(self) -> list[str]:
        """Extract URLs from the message."""
        ...

    async def download_attachment(self, tmp_dir: str) -> tuple[str, str] | None:
        """Download media attachment. Returns (file_path, media_type) or None."""
        ...
