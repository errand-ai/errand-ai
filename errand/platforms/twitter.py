import logging

from platforms.base import Platform, PlatformCapability, PlatformInfo, PostResult

logger = logging.getLogger(__name__)


class TwitterPlatform(Platform):
    def info(self) -> PlatformInfo:
        return PlatformInfo(
            id="twitter",
            label="Twitter/X",
            capabilities={PlatformCapability.POST, PlatformCapability.MEDIA, PlatformCapability.ANALYTICS, PlatformCapability.SEARCH},
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

    async def reply(self, tweet_id: str, message: str, **kwargs) -> PostResult:
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
            response = client.create_tweet(text=message, in_reply_to_tweet_id=tweet_id)
            reply_id = response.data["id"]
            user = client.get_me()
            username = user.data.username if user.data else "i"
            url = f"https://x.com/{username}/status/{reply_id}"
            return PostResult(success=True, url=url)
        except Exception as e:
            return PostResult(success=False, error=str(e))

    async def like(self, tweet_id: str, **kwargs) -> bool:
        import tweepy

        credentials = kwargs.get("credentials")
        if not credentials:
            raise ValueError("No credentials provided")

        client = tweepy.Client(
            consumer_key=credentials["api_key"],
            consumer_secret=credentials["api_secret"],
            access_token=credentials["access_token"],
            access_token_secret=credentials["access_secret"],
        )
        client.like(tweet_id=tweet_id)
        return True

    async def retweet(self, tweet_id: str, **kwargs) -> bool:
        import tweepy

        credentials = kwargs.get("credentials")
        if not credentials:
            raise ValueError("No credentials provided")

        client = tweepy.Client(
            consumer_key=credentials["api_key"],
            consumer_secret=credentials["api_secret"],
            access_token=credentials["access_token"],
            access_token_secret=credentials["access_secret"],
        )
        client.retweet(tweet_id=tweet_id)
        return True

    async def get_metrics(self, tweet_id: str, **kwargs) -> dict:
        import tweepy

        credentials = kwargs.get("credentials")
        if not credentials:
            raise ValueError("No credentials provided")

        client = tweepy.Client(
            consumer_key=credentials["api_key"],
            consumer_secret=credentials["api_secret"],
            access_token=credentials["access_token"],
            access_token_secret=credentials["access_secret"],
        )
        response = client.get_tweet(
            tweet_id,
            tweet_fields=["public_metrics", "non_public_metrics", "organic_metrics", "created_at", "text"],
        )
        if not response.data:
            raise ValueError(f"Tweet {tweet_id} not found")

        tweet = response.data
        result: dict = {
            "tweet_id": str(tweet.id),
            "text": tweet.text,
            "created_at": tweet.created_at.isoformat() if tweet.created_at else "",
        }
        if tweet.public_metrics:
            result["public_metrics"] = dict(tweet.public_metrics)
        if tweet.non_public_metrics:
            result["non_public_metrics"] = dict(tweet.non_public_metrics)
        if tweet.organic_metrics:
            result["organic_metrics"] = dict(tweet.organic_metrics)
        return result

    async def get_my_tweets(self, max_results: int = 10, **kwargs) -> list[dict]:
        import tweepy

        credentials = kwargs.get("credentials")
        if not credentials:
            raise ValueError("No credentials provided")

        client = tweepy.Client(
            consumer_key=credentials["api_key"],
            consumer_secret=credentials["api_secret"],
            access_token=credentials["access_token"],
            access_token_secret=credentials["access_secret"],
        )
        me = client.get_me()
        if not me.data:
            raise ValueError("Could not retrieve authenticated user")

        response = client.get_users_tweets(
            me.data.id,
            max_results=max(5, min(max_results, 100)),
            tweet_fields=["public_metrics", "non_public_metrics", "organic_metrics", "created_at", "text"],
        )

        tweets = []
        if response.data:
            for tweet in response.data:
                t: dict = {
                    "tweet_id": str(tweet.id),
                    "text": tweet.text,
                    "created_at": tweet.created_at.isoformat() if tweet.created_at else "",
                }
                if tweet.public_metrics:
                    t["public_metrics"] = dict(tweet.public_metrics)
                if tweet.non_public_metrics:
                    t["non_public_metrics"] = dict(tweet.non_public_metrics)
                if tweet.organic_metrics:
                    t["organic_metrics"] = dict(tweet.organic_metrics)
                tweets.append(t)
        return tweets

    async def search(self, query: str, **kwargs) -> dict:
        import tweepy

        credentials = kwargs.get("credentials")
        if not credentials:
            raise ValueError("No credentials provided")

        max_results = kwargs.get("max_results", 10)
        max_results = max(10, min(max_results, 100))

        client = tweepy.Client(
            consumer_key=credentials["api_key"],
            consumer_secret=credentials["api_secret"],
            access_token=credentials["access_token"],
            access_token_secret=credentials["access_secret"],
        )
        try:
            response = client.search_recent_tweets(
                query=query,
                max_results=max_results,
                tweet_fields=["created_at", "public_metrics", "text"],
                expansions=["author_id"],
                user_fields=["username"],
            )
        except tweepy.Forbidden:
            raise ValueError(
                "Twitter search requires X API Basic tier or higher. "
                "Current credentials do not have search access."
            )

        # Build username lookup from includes
        users = {}
        if response.includes and "users" in response.includes:
            for user in response.includes["users"]:
                users[str(user.id)] = user.username

        tweets = []
        if response.data:
            for tweet in response.data:
                tweets.append({
                    "tweet_id": str(tweet.id),
                    "text": tweet.text,
                    "created_at": tweet.created_at.isoformat() if tweet.created_at else "",
                    "author_id": str(tweet.author_id) if tweet.author_id else "",
                    "author_username": users.get(str(tweet.author_id), ""),
                    "public_metrics": dict(tweet.public_metrics) if tweet.public_metrics else {},
                })
        return {"query": query, "results": tweets}
