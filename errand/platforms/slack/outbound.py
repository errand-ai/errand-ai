"""Outbound message posting orchestration with auto-join, error mapping, and rate-limit translation.

Used by the slack_message and slack_reply MCP tools. Raw API I/O lives on
SlackClient; this layer adds the policy: auto-join public channels on
``not_in_channel``, translate HTTP 429 to a structured error, and surface
Slack's error codes verbatim.
"""
import logging

import httpx

from platforms.slack.client import SlackClient, text_to_blocks
from platforms.slack.identity import evict_channel_cache_entry

logger = logging.getLogger(__name__)


def _is_public_channel_id(channel_id: str) -> bool:
    """Public channels start with C. Private groups start with G; DMs with D."""
    return bool(channel_id) and channel_id[0] == "C"


async def post_message_with_policy(
    client: SlackClient,
    bot_token: str,
    channel: str,
    *,
    text: str | None = None,
    blocks: list | None = None,
    thread_ts: str | None = None,
) -> dict:
    """Post a Slack message and return ``{ok, channel, ts, error?}``.

    Behavior:
    - If ``blocks`` is omitted but ``text`` is given, wrap text in a section block.
    - On HTTP 429, return ``{ok: false, error: "rate_limited; retry after Ns"}``.
    - On Slack ``not_in_channel`` for a public channel, attempt ``conversations.join`` and retry once.
    - On Slack ``channel_not_found``, evict the channel-name cache entry (if any) so the next
      call can re-resolve a renamed channel.
    - All other Slack errors are surfaced verbatim in the ``error`` field.
    """
    # Build effective blocks: explicit blocks take precedence; otherwise wrap text.
    effective_blocks = blocks if blocks else (text_to_blocks(text) if text else None)

    try:
        resp = await client.post_message(
            bot_token,
            channel,
            blocks=effective_blocks,
            text=text,
            thread_ts=thread_ts,
        )
    except httpx.HTTPStatusError as e:
        if e.response.status_code == 429:
            retry_after = e.response.headers.get("Retry-After", "?")
            return {
                "ok": False,
                "channel": channel,
                "ts": "",
                "error": f"rate_limited; retry after {retry_after} seconds",
            }
        logger.exception("HTTP error from chat.postMessage for channel %s", channel)
        return {
            "ok": False,
            "channel": channel,
            "ts": "",
            "error": f"http_{e.response.status_code}",
        }
    except Exception as e:
        logger.exception("Unexpected error from chat.postMessage for channel %s", channel)
        return {"ok": False, "channel": channel, "ts": "", "error": str(e)}

    if resp.get("ok"):
        return {
            "ok": True,
            "channel": resp.get("channel", channel),
            "ts": resp.get("ts", ""),
        }

    err = resp.get("error", "unknown")

    # Auto-join only for public channels we are not in
    if err == "not_in_channel" and _is_public_channel_id(channel):
        try:
            join_resp = await client.join_channel(bot_token, channel)
        except Exception as exc:
            logger.exception("Auto-join failed for channel %s", channel)
            return {
                "ok": False,
                "channel": channel,
                "ts": "",
                "error": f"not_in_channel; auto-join failed: {exc}",
            }
        if not join_resp.get("ok"):
            return {
                "ok": False,
                "channel": channel,
                "ts": "",
                "error": f"not_in_channel; auto-join failed: {join_resp.get('error', 'unknown')}",
            }
        # Retry once after joining
        try:
            retry_resp = await client.post_message(
                bot_token,
                channel,
                blocks=effective_blocks,
                text=text,
                thread_ts=thread_ts,
            )
        except Exception as exc:
            logger.exception("Retry after auto-join failed for channel %s", channel)
            return {"ok": False, "channel": channel, "ts": "", "error": str(exc)}
        if retry_resp.get("ok"):
            return {
                "ok": True,
                "channel": retry_resp.get("channel", channel),
                "ts": retry_resp.get("ts", ""),
            }
        return {
            "ok": False,
            "channel": channel,
            "ts": "",
            "error": retry_resp.get("error", "unknown"),
        }

    if err == "channel_not_found":
        evict_channel_cache_entry(channel)

    return {"ok": False, "channel": channel, "ts": "", "error": err}
