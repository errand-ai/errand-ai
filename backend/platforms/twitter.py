import logging

from platforms.base import Platform, PlatformCapability, PlatformInfo, PostResult

logger = logging.getLogger(__name__)


class TwitterPlatform(Platform):
    def info(self) -> PlatformInfo:
        return PlatformInfo(
            id="twitter",
            label="Twitter/X",
            capabilities={PlatformCapability.POST, PlatformCapability.MEDIA},
            credential_schema=[
                {"key": "api_key", "label": "API Key", "type": "password", "required": True},
                {"key": "api_secret", "label": "API Secret", "type": "password", "required": True},
                {"key": "access_token", "label": "Access Token", "type": "password", "required": True},
                {"key": "access_secret", "label": "Access Token Secret", "type": "password", "required": True},
            ],
        )

    async def verify_credentials(self, credentials: dict) -> bool:
        import tweepy

        try:
            client = tweepy.Client(
                consumer_key=credentials["api_key"],
                consumer_secret=credentials["api_secret"],
                access_token=credentials["access_token"],
                access_token_secret=credentials["access_secret"],
            )
            user = client.get_me()
            return user.data is not None
        except Exception:
            logger.exception("Twitter credential verification failed")
            return False

    async def post(self, message: str, **kwargs) -> PostResult:
        import tweepy

        credentials = kwargs.get("credentials")
        if not credentials:
            return PostResult(success=False, error="No credentials provided")

        try:
            client = tweepy.Client(
                consumer_key=credentials["api_key"],
                consumer_secret=credentials["api_secret"],
                access_token=credentials["access_token"],
                access_token_secret=credentials["access_secret"],
            )
            response = client.create_tweet(text=message)
            tweet_id = response.data["id"]
            user = client.get_me()
            username = user.data.username if user.data else "i"
            url = f"https://x.com/{username}/status/{tweet_id}"
            return PostResult(success=True, url=url)
        except Exception as e:
            return PostResult(success=False, error=str(e))
