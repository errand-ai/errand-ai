"""Outbound-message allowlist for the slack_message / slack_reply MCP tools.

Setting key: ``slack_outbound_allowlist`` — a JSON list of channel/user
identifiers in any form accepted by ``resolve_slack_target`` (channel ID,
``#channel``, user ID, ``@user``, email, or bare name).

Default behavior (empty list or unset): unrestricted within the workspace.
Any reachable channel or user can be targeted. Workspaces wanting strict
control populate the list explicitly.
"""
import logging
import re

from platforms.slack.identity import (
    TargetResolutionError,
    resolve_slack_target,
)

logger = logging.getLogger(__name__)

_EMAIL_RE = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")


def _redact_for_log(entry: str) -> str:
    """Redact identifiers that may carry PII before they hit operational logs.

    Slack IDs (C…/U…/D…/G…), channel names (#…), and the leading-@ usernames
    are safe to log directly — they are workspace-scoped identifiers, not PII.
    Emails and bare strings (which could be a username or anything else) are
    rendered as a kind hint plus a short fingerprint so log readers can still
    correlate without seeing the underlying value.
    """
    if not isinstance(entry, str) or not entry:
        return "<empty>"
    if entry.startswith("#") or entry.startswith("@") or re.match(r"^[CDGUW][A-Z0-9]{8,}$", entry):
        return entry
    if _EMAIL_RE.match(entry):
        # Keep just the domain — useful for triage, not enough to identify the user
        return f"<email:{entry.split('@', 1)[1]}>"
    return f"<opaque:{len(entry)}chars>"


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
            logger.warning("Allowlist entry %s could not be resolved; skipping", _redact_for_log(entry))
            continue
        except Exception:
            logger.exception("Unexpected error resolving allowlist entry %s", _redact_for_log(entry))
            continue
        if entry_id == resolved_id:
            return True
    return False
