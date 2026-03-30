"""Platform-agnostic authorization."""

import functools
import logging

logger = logging.getLogger(__name__)


def authorized(func):
    """Decorator that restricts commands to allowed user IDs."""

    @functools.wraps(func)
    async def wrapper(ctx, *args, **kwargs):
        config = ctx.get_config()
        user_id = ctx.user_id

        # Extract platform and numeric ID
        parts = user_id.split(":", 1)
        if len(parts) != 2:
            logger.warning("Malformed user_id: %s", user_id)
            await ctx.message.reply(f"Unauthorized.")
            return

        platform, raw_id = parts

        # Check against platform-specific allowed IDs
        platform_config = getattr(config, platform, None)
        if platform_config is None:
            await ctx.message.reply("Platform not configured.")
            return

        if raw_id not in platform_config.allowed_ids:
            logger.warning("Unauthorized access from %s", user_id)
            await ctx.message.reply(f"Unauthorized. Your ID: {raw_id}")
            return

        return await func(ctx, *args, **kwargs)

    return wrapper
