"""Slack platform integration.

Slack App Configuration Requirements:
  Bot Token Scopes:
    - chat:write        Post and update messages in channels
    - users:read        Resolve user IDs to email addresses
    - users:read.email  Access user email addresses
    - commands          Respond to slash commands

  Event Subscriptions:
    - app_mentions:read  Receive @mention events
    - Request URL: https://<domain>/slack/events

  Interactivity & Shortcuts:
    - Request URL: https://<domain>/slack/interactions
    - Required, not optional: `/task new` and mentions reply with a draft whose
      answers and Run button arrive here, so without it no task can be created
      from Slack. Behind NAT, use the errand-cloud relay, which forwards
      interactivity as well as commands and events.

  Slash Commands:
    - /task → https://<domain>/slack/commands
"""
import logging

from platforms.base import Platform, PlatformCapability, PlatformInfo

logger = logging.getLogger(__name__)


class SlackPlatform(Platform):
    def info(self) -> PlatformInfo:
        return PlatformInfo(
            id="slack",
            label="Slack",
            capabilities={PlatformCapability.COMMANDS, PlatformCapability.WEBHOOKS},
            credential_schema=[
                {"key": "bot_token", "label": "Bot Token", "type": "password", "required": True},
                {"key": "signing_secret", "label": "Signing Secret", "type": "password", "required": True},
            ],
        )

    async def verify_credentials(self, credentials: dict) -> bool:
        from slack_sdk.web.async_client import AsyncWebClient

        try:
            client = AsyncWebClient(token=credentials["bot_token"])
            await client.auth_test()
            return True
        except Exception:
            logger.exception("Slack credential verification failed")
            return False
