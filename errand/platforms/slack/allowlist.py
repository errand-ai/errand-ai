"""Outbound-message allowlist for the slack_message / slack_reply MCP tools.

Setting key: ``slack_outbound_allowlist`` — a JSON list of channel/user
identifiers in any form accepted by ``resolve_slack_target`` (channel ID,
``#channel``, user ID, ``@user``, email, or bare name).

Default behavior (empty list or unset): unrestricted within the workspace.
Any reachable channel or user can be targeted. Workspaces wanting strict
control populate the list explicitly.
"""
import logging

from platforms.slack.identity import (
    TargetResolutionError,
    resolve_slack_target,
)

logger = logging.getLogger(__name__)


async def check_outbound_allowlist(
    bot_token: str,
    resolved_id: str,
    allowlist: list[str] | None,
) -> bool:
    """Return True if `resolved_id` is permitted under `allowlist`.

    `allowlist` entries are resolved to Slack IDs and compared against
    `resolved_id`. Empty / None allowlist always permits.

    Entries that fail to resolve (renamed channel, missing user, etc.)
    are skipped with a warning log — they cannot be matched.
    """
    if not allowlist:
        return True

    for entry in allowlist:
        if not isinstance(entry, str) or not entry.strip():
            continue
        try:
            _, entry_id = await resolve_slack_target(entry, bot_token)
        except TargetResolutionError:
            logger.warning("Allowlist entry %r could not be resolved; skipping", entry)
            continue
        except Exception:
            logger.exception("Unexpected error resolving allowlist entry %r", entry)
            continue
        if entry_id == resolved_id:
            return True
    return False
