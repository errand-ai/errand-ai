"""Lightweight Slack Web API client using httpx."""
import logging

import httpx

logger = logging.getLogger(__name__)

SLACK_API_BASE = "https://slack.com/api"


def text_to_blocks(text: str) -> list:
    """Wrap a plain mrkdwn string in a single section block.

    Used so all SlackClient call paths flow through a uniform `blocks` payload
    while still letting callers (and the LLM-driven tools) supply just text.
    """
    return [{"type": "section", "text": {"type": "mrkdwn", "text": text}}]


class SlackClient:
    """Thin wrapper around Slack Web API methods needed for message posting/updating."""

    async def post_message(
        self,
        token: str,
        channel: str,
        blocks: list | None = None,
        *,
        text: str | None = None,
        thread_ts: str | None = None,
    ) -> dict:
        """Post a message to a Slack channel or DM. Returns the full Slack API response.

        Either `blocks` or `text` (or both) must be provided. When both are present,
        `blocks` is used for rendering and `text` becomes the notification fallback,
        matching Slack's own contract for chat.postMessage.
        """
        payload: dict = {"channel": channel}
        if text is not None:
            payload["text"] = text
        if blocks:
            payload["blocks"] = blocks
        if thread_ts:
            payload["thread_ts"] = thread_ts

        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{SLACK_API_BASE}/chat.postMessage",
                headers={"Authorization": f"Bearer {token}"},
                json=payload,
            )
            resp.raise_for_status()
            data = resp.json()
            if not data.get("ok"):
                logger.error("chat.postMessage failed: %s", data.get("error"))
            return data

    async def post_response_url(self, response_url: str, blocks: list, *, ephemeral: bool = True) -> None:
        """Post a message to a Slack response_url (interaction follow-up).

        Unlike Slack API methods, response_url does not need a bearer token — the URL
        itself is a one-time-use signed webhook.
        """
        payload: dict = {
            "response_type": "ephemeral" if ephemeral else "in_channel",
            "replace_original": False,
            "blocks": blocks,
        }
        async with httpx.AsyncClient() as client:
            resp = await client.post(response_url, json=payload)
            resp.raise_for_status()

    async def update_message(self, token: str, channel: str, ts: str, blocks: list) -> dict:
        """Update an existing Slack message. Returns the API response JSON."""
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{SLACK_API_BASE}/chat.update",
                headers={"Authorization": f"Bearer {token}"},
                json={"channel": channel, "ts": ts, "blocks": blocks},
            )
            resp.raise_for_status()
            data = resp.json()
            if not data.get("ok"):
                logger.error("chat.update failed: %s", data.get("error"))
            return data

    async def join_channel(self, token: str, channel_id: str) -> dict:
        """Join a public channel via conversations.join. Returns the API response.

        Requires the `channels:join` scope. Only works for public channels;
        private channels and DMs cannot be joined this way.
        """
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{SLACK_API_BASE}/conversations.join",
                headers={"Authorization": f"Bearer {token}"},
                json={"channel": channel_id},
            )
            resp.raise_for_status()
            data = resp.json()
            if not data.get("ok"):
                logger.warning("conversations.join failed for %s: %s", channel_id, data.get("error"))
            return data
