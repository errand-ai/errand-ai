import logging
import time

from slack_sdk.web.async_client import AsyncWebClient

logger = logging.getLogger(__name__)

# Module-level cache: {user_id: (email_or_none, timestamp)}
_email_cache: dict[str, tuple[str | None, float]] = {}
_CACHE_TTL = 3600  # 1 hour


async def resolve_slack_email(user_id: str, bot_token: str) -> str | None:
    """Resolve a Slack user ID to their email address.

    Results (including None) are cached for 1 hour to avoid repeated API calls.
    """
    now = time.time()

    cached = _email_cache.get(user_id)
    if cached is not None:
        email, ts = cached
        if now - ts < _CACHE_TTL:
            return email

    try:
        client = AsyncWebClient(token=bot_token)
        response = await client.users_info(user=user_id)
        email = response["user"]["profile"].get("email")
    except Exception:
        logger.exception("Failed to resolve Slack email for user %s", user_id)
        return None

    _email_cache[user_id] = (email, now)
    return email
