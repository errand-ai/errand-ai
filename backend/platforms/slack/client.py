"""Lightweight Slack Web API client using httpx."""
import logging

import httpx

logger = logging.getLogger(__name__)

SLACK_API_BASE = "https://slack.com/api"


class SlackClient:
    """Thin wrapper around Slack Web API methods needed for message posting/updating."""

    async def post_message(self, token: str, channel: str, blocks: list) -> dict:
        """Post a message to a Slack channel. Returns the API response JSON."""
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{SLACK_API_BASE}/chat.postMessage",
                headers={"Authorization": f"Bearer {token}"},
                json={"channel": channel, "blocks": blocks},
            )
            resp.raise_for_status()
            data = resp.json()
            if not data.get("ok"):
                logger.error("chat.postMessage failed: %s", data.get("error"))
            return data

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
