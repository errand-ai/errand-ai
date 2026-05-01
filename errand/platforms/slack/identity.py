import logging
import re
import time
from typing import Literal

from slack_sdk.web.async_client import AsyncWebClient

logger = logging.getLogger(__name__)

_CACHE_TTL = 3600  # 1 hour

# Module-level caches: each maps key -> (resolved_id_or_none, timestamp)
_email_cache: dict[str, tuple[str | None, float]] = {}
_channel_name_cache: dict[str, tuple[str | None, float]] = {}
_user_name_cache: dict[str, tuple[str | None, float]] = {}

# Slack ID patterns. Channel/conversation IDs start with C (public), G (private group),
# or D (DM). User IDs start with U or W (Enterprise Grid).
_CHANNEL_ID_RE = re.compile(r"^[CDG][A-Z0-9]{8,}$")
_USER_ID_RE = re.compile(r"^[UW][A-Z0-9]{8,}$")
_EMAIL_RE = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")


def _cache_get(cache: dict, key: str) -> tuple[bool, str | None]:
    """Return (hit, value). hit=False means caller must resolve."""
    entry = cache.get(key)
    if entry is None:
        return False, None
    value, ts = entry
    if time.time() - ts >= _CACHE_TTL:
        cache.pop(key, None)
        return False, None
    return True, value


def _cache_put(cache: dict, key: str, value: str | None) -> None:
    cache[key] = (value, time.time())


def evict_channel_cache_entry(channel_id_or_name: str) -> None:
    """Remove any cached channel-name entry that resolved to the given id (or matches the name).

    Called when Slack returns channel_not_found so a renamed channel can be re-resolved.
    """
    # Drop direct name hit
    _channel_name_cache.pop(channel_id_or_name, None)
    _channel_name_cache.pop(channel_id_or_name.lstrip("#"), None)
    # Drop entries that resolved to this id
    stale = [k for k, (v, _) in _channel_name_cache.items() if v == channel_id_or_name]
    for k in stale:
        _channel_name_cache.pop(k, None)


async def resolve_slack_email(user_id: str, bot_token: str) -> str | None:
    """Resolve a Slack user ID to their email address.

    Results (including None) are cached for 1 hour to avoid repeated API calls.
    """
    hit, cached = _cache_get(_email_cache, user_id)
    if hit:
        return cached

    try:
        client = AsyncWebClient(token=bot_token)
        response = await client.users_info(user=user_id)
        email = response["user"]["profile"].get("email")
    except Exception:
        logger.exception("Failed to resolve Slack email for user %s", user_id)
        return None

    _cache_put(_email_cache, user_id, email)
    return email


async def _resolve_user_by_email(email: str, bot_token: str) -> str | None:
    """Look up a user ID by email via users.lookupByEmail. Cached on success only.

    A transient API failure (network, 5xx, rate limit) does NOT poison the cache —
    the next call will retry. Successful "user not found" results ARE cached so we
    don't keep hammering Slack for known-missing emails.
    """
    hit, cached = _cache_get(_email_cache, f"email:{email}")
    if hit:
        return cached
    try:
        client = AsyncWebClient(token=bot_token)
        resp = await client.users_lookupByEmail(email=email)
        user_id = resp.get("user", {}).get("id")
    except Exception:
        logger.exception("Failed to resolve Slack user by email %s", email)
        return None
    _cache_put(_email_cache, f"email:{email}", user_id)
    return user_id


async def _resolve_channel_by_name(name: str, bot_token: str) -> str | None:
    """Look up a channel ID by its name (without leading #). Cached on success only.

    Transient errors are not cached so retries can succeed; "channel not found" IS
    cached to avoid repeated full-pagination scans for known-missing names.
    """
    hit, cached = _cache_get(_channel_name_cache, name)
    if hit:
        return cached

    found_id: str | None = None
    try:
        client = AsyncWebClient(token=bot_token)
        cursor: str | None = None
        while True:
            kwargs = {"limit": 1000, "exclude_archived": True, "types": "public_channel,private_channel"}
            if cursor:
                kwargs["cursor"] = cursor
            resp = await client.conversations_list(**kwargs)
            for ch in resp.get("channels", []):
                if ch.get("name") == name:
                    found_id = ch.get("id")
                    break
            if found_id:
                break
            cursor = resp.get("response_metadata", {}).get("next_cursor") or None
            if not cursor:
                break
    except Exception:
        logger.exception("Failed to resolve Slack channel by name %s", name)
        return None

    _cache_put(_channel_name_cache, name, found_id)
    return found_id


async def _resolve_user_by_username(username: str, bot_token: str) -> str | None:
    """Look up a user ID by username (without leading @). Cached on success only.

    Transient errors are not cached; "user not found" IS cached.
    """
    hit, cached = _cache_get(_user_name_cache, username)
    if hit:
        return cached

    found_id: str | None = None
    try:
        client = AsyncWebClient(token=bot_token)
        cursor: str | None = None
        while True:
            kwargs = {"limit": 1000}
            if cursor:
                kwargs["cursor"] = cursor
            resp = await client.users_list(**kwargs)
            for u in resp.get("members", []):
                if u.get("deleted"):
                    continue
                if u.get("name") == username or u.get("profile", {}).get("display_name") == username:
                    found_id = u.get("id")
                    break
            if found_id:
                break
            cursor = resp.get("response_metadata", {}).get("next_cursor") or None
            if not cursor:
                break
    except Exception:
        logger.exception("Failed to resolve Slack user by username %s", username)
        return None

    _cache_put(_user_name_cache, username, found_id)
    return found_id


# In-memory cache: user_id -> (D… channel_id_or_none, timestamp)
_dm_channel_cache: dict[str, tuple[str | None, float]] = {}


async def open_dm_channel(user_id: str, bot_token: str) -> str | None:
    """Open (or find) the IM conversation with a user and return its D… channel ID.

    ``chat.postMessage`` with a user ID as ``channel`` works in many cases but is not
    documented as the canonical path; ``conversations.open`` is the supported way to
    materialize a DM channel ID. Cached for 1 hour because IM channel IDs are stable
    once opened.
    """
    hit, cached = _cache_get(_dm_channel_cache, user_id)
    if hit:
        return cached
    try:
        client = AsyncWebClient(token=bot_token)
        resp = await client.conversations_open(users=user_id)
        channel_id = resp.get("channel", {}).get("id")
    except Exception:
        logger.exception("Failed to open DM channel for user %s", user_id)
        return None
    _cache_put(_dm_channel_cache, user_id, channel_id)
    return channel_id


class TargetResolutionError(Exception):
    """Raised when a target string cannot be unambiguously resolved."""


async def resolve_slack_target(target: str, bot_token: str) -> tuple[Literal["channel", "user"], str]:
    """Resolve a target string to (kind, slack_id).

    Resolution precedence:
      1. Conversation IDs (C/D/G prefix) → channel
      2. User IDs (U/W prefix) → user
      3. Email pattern → user (via users.lookupByEmail)
      4. Leading '#' → channel by name (without prefix)
      5. Leading '@' → user by name (without prefix)
      6. Bare names → try channel and user; ambiguous match raises TargetResolutionError

    Raises TargetResolutionError if the target cannot be resolved or is ambiguous.
    """
    if not target or not target.strip():
        raise TargetResolutionError("Target is empty")

    raw = target.strip()

    if _CHANNEL_ID_RE.match(raw):
        return ("channel", raw)
    if _USER_ID_RE.match(raw):
        return ("user", raw)

    if _EMAIL_RE.match(raw):
        user_id = await _resolve_user_by_email(raw, bot_token)
        if user_id is None:
            raise TargetResolutionError(f"No Slack user found for email {raw}")
        return ("user", user_id)

    if raw.startswith("#"):
        name = raw[1:]
        ch_id = await _resolve_channel_by_name(name, bot_token)
        if ch_id is None:
            raise TargetResolutionError(f"No Slack channel found named #{name}")
        return ("channel", ch_id)

    if raw.startswith("@"):
        name = raw[1:]
        u_id = await _resolve_user_by_username(name, bot_token)
        if u_id is None:
            raise TargetResolutionError(f"No Slack user found named @{name}")
        return ("user", u_id)

    # Bare name — try both, error on ambiguity
    ch_id = await _resolve_channel_by_name(raw, bot_token)
    u_id = await _resolve_user_by_username(raw, bot_token)
    if ch_id and u_id:
        raise TargetResolutionError(
            f"Ambiguous target {raw!r} — matches both channel #{raw} and user @{raw}; prefix with '#' or '@'"
        )
    if ch_id:
        return ("channel", ch_id)
    if u_id:
        return ("user", u_id)
    raise TargetResolutionError(f"No Slack channel or user matches {raw!r}")
