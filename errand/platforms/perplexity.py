import logging
import httpx

from platforms.base import Platform, PlatformCapability, PlatformInfo

logger = logging.getLogger(__name__)


class PerplexityPlatform(Platform):
    def info(self) -> PlatformInfo:
        return PlatformInfo(
            id="perplexity",
            label="Perplexity",
            capabilities={PlatformCapability.TOOL_PROVIDER},
            credential_schema=[
                {"key": "api_key", "label": "API Key", "type": "password", "required": True},
            ],
        )

    async def verify_credentials(self, credentials: dict) -> bool:
        """Verify credentials by making a minimal API call to Perplexity.

        Note: This makes a real API call (with max_tokens=1) which incurs a small cost.
        """
        api_key = credentials.get("api_key")
        if not api_key:
            return False

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.post(
                    "https://api.perplexity.ai/chat/completions",
                    headers={
                        "Authorization": f"Bearer {api_key}",
                        "Content-Type": "application/json",
                    },
                    json={
                        "model": "llama-3.1-sonar-small-128k-online",
                        "messages": [
                            {"role": "user", "content": "test"}
                        ],
                        "max_tokens": 1,
                    },
                )
                return response.status_code == 200
        except Exception:
            logger.exception("Perplexity credential verification failed")
            return False
