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
