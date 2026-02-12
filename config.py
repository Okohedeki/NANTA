import os
from dataclasses import dataclass

from dotenv import load_dotenv

load_dotenv()


@dataclass(frozen=True)
class Config:
    bot_token: str
    allowed_chat_ids: frozenset[int]
    default_cwd: str
    default_model: str
    claude_timeout: int
    shell_timeout: int
    max_budget_usd: float


def load_config() -> Config:
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
    if not token or token == "your-bot-token-here":
        raise ValueError("TELEGRAM_BOT_TOKEN not set in .env")

    raw_ids = os.environ.get("ALLOWED_CHAT_IDS", "")
    chat_ids = frozenset(
        int(cid.strip()) for cid in raw_ids.split(",") if cid.strip()
    )

    return Config(
        bot_token=token,
        allowed_chat_ids=chat_ids,
        default_cwd=os.environ.get("DEFAULT_CWD", os.getcwd()),
        default_model=os.environ.get("DEFAULT_MODEL", "sonnet"),
        claude_timeout=int(os.environ.get("CLAUDE_TIMEOUT", "300")),
        shell_timeout=int(os.environ.get("SHELL_TIMEOUT", "60")),
        max_budget_usd=float(os.environ.get("MAX_BUDGET_USD", "1.0")),
    )
