"""Tests for RSS feed tool and new Twitter engagement/analytics/search MCP tools."""

import json
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# 11.1 read_rss_feed tests
# ---------------------------------------------------------------------------

VALID_RSS = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
  <channel>
    <title>Test Blog</title>
    <link>https://example.com</link>
    <description>A test feed</description>
    <item>
      <title>Post One</title>
      <link>https://example.com/post-one</link>
      <pubDate>Sat, 26 Apr 2026 12:00:00 GMT</pubDate>
      <description>First post summary</description>
    </item>
    <item>
      <title>Post Two</title>
      <link>https://example.com/post-two</link>
      <pubDate>Fri, 25 Apr 2026 12:00:00 GMT</pubDate>
      <description>Second post summary</description>
    </item>
    <item>
      <title>Post Three</title>
      <link>https://example.com/post-three</link>
      <pubDate>Thu, 24 Apr 2026 12:00:00 GMT</pubDate>
      <description>Third post summary</description>
    </item>
  </channel>
</rss>"""

VALID_ATOM = """<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <title>Atom Feed</title>
  <link href="https://example.com"/>
  <entry>
    <title>Atom Entry</title>
    <link href="https://example.com/atom-entry"/>
    <updated>2026-04-26T10:00:00Z</updated>
    <summary>An Atom entry</summary>
  </entry>
</feed>"""

RSS_NO_DATES = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
  <channel>
    <title>No Dates</title>
    <link>https://example.com</link>
    <item>
      <title>Undated Post</title>
      <link>https://example.com/undated</link>
      <description>No date here</description>
    </item>
  </channel>
</rss>"""


@pytest.fixture
def _mock_httpx_rss():
    """Provide a helper that patches httpx to return given content."""
    from contextlib import asynccontextmanager

    def _make(content: str, status_code: int = 200, raise_exc=None):
        mock_resp = MagicMock()
        mock_resp.text = content
        mock_resp.status_code = status_code
        mock_resp.raise_for_status = MagicMock()
        if status_code >= 400:
            import httpx
            mock_resp.raise_for_status.side_effect = httpx.HTTPStatusError(
                "error", request=MagicMock(), response=mock_resp,
            )

        @asynccontextmanager
        async def mock_client(*args, **kwargs):
            client = AsyncMock()
            if raise_exc:
                client.get.side_effect = raise_exc
            else:
                client.get.return_value = mock_resp
            yield client

        return patch("mcp_server.httpx.AsyncClient", side_effect=mock_client)
    return _make


async def test_read_rss_feed_valid_rss(_mock_httpx_rss):
    """Valid RSS feed returns structured items."""
    from mcp_server import read_rss_feed

    with _mock_httpx_rss(VALID_RSS):
        result = json.loads(await read_rss_feed("https://example.com/feed"))

    assert result["feed"]["title"] == "Test Blog"
    assert len(result["items"]) == 3
    assert result["items"][0]["title"] == "Post One"  # newest first


async def test_read_rss_feed_valid_atom(_mock_httpx_rss):
    """Valid Atom feed returns structured items."""
    from mcp_server import read_rss_feed

    with _mock_httpx_rss(VALID_ATOM):
        result = json.loads(await read_rss_feed("https://example.com/atom"))

    assert result["feed"]["title"] == "Atom Feed"
    assert len(result["items"]) == 1
    assert result["items"][0]["title"] == "Atom Entry"


async def test_read_rss_feed_max_items(_mock_httpx_rss):
    """max_items limits the number of returned items."""
    from mcp_server import read_rss_feed

    with _mock_httpx_rss(VALID_RSS):
        result = json.loads(await read_rss_feed("https://example.com/feed", max_items=2))

    assert len(result["items"]) == 2


async def test_read_rss_feed_since_filter(_mock_httpx_rss):
    """since parameter filters out older items."""
    from mcp_server import read_rss_feed

    with _mock_httpx_rss(VALID_RSS):
        result = json.loads(await read_rss_feed(
            "https://example.com/feed", since="2026-04-25T00:00:00Z",
        ))

    # Only Post One (Apr 26) and Post Two (Apr 25 12:00) should pass
    assert len(result["items"]) == 2
    assert all("2026-04-2" in item["published"] for item in result["items"])


async def test_read_rss_feed_missing_dates(_mock_httpx_rss):
    """Items without dates have empty published field."""
    from mcp_server import read_rss_feed

    with _mock_httpx_rss(RSS_NO_DATES):
        result = json.loads(await read_rss_feed("https://example.com/feed"))

    assert len(result["items"]) == 1
    assert result["items"][0]["published"] == ""


async def test_read_rss_feed_fetch_failure(_mock_httpx_rss):
    """Network errors return JSON error."""
    from mcp_server import read_rss_feed

    with _mock_httpx_rss("", raise_exc=Exception("Connection refused")):
        result = json.loads(await read_rss_feed("https://example.com/feed"))

    assert "error" in result


async def test_read_rss_feed_invalid_content(_mock_httpx_rss):
    """HTML (non-feed) content returns error."""
    from mcp_server import read_rss_feed

    with _mock_httpx_rss("<html><body>Not a feed</body></html>"):
        result = json.loads(await read_rss_feed("https://example.com/page"))

    assert "error" in result
    assert "valid" in result["error"].lower() or "feed" in result["error"].lower()


async def test_read_rss_feed_timeout(_mock_httpx_rss):
    """Timeout returns JSON error."""
    import httpx
    from mcp_server import read_rss_feed

    with _mock_httpx_rss("", raise_exc=httpx.TimeoutException("timeout")):
        result = json.loads(await read_rss_feed("https://example.com/feed"))

    assert "error" in result
    assert "timeout" in result["error"].lower()


# ---------------------------------------------------------------------------
# Helper: set up Twitter env + registry
# ---------------------------------------------------------------------------

@pytest.fixture
def twitter_env(monkeypatch):
    """Set Twitter env vars and register the platform."""
    monkeypatch.setenv("TWITTER_API_KEY", "key")
    monkeypatch.setenv("TWITTER_API_SECRET", "secret")
    monkeypatch.setenv("TWITTER_ACCESS_TOKEN", "token")
    monkeypatch.setenv("TWITTER_ACCESS_SECRET", "access")

    from platforms import get_registry
    from platforms.twitter import TwitterPlatform
    registry = get_registry()
    registry.register(TwitterPlatform())


@pytest.fixture
def no_twitter_env(monkeypatch):
    """Ensure no Twitter env vars are set."""
    monkeypatch.delenv("TWITTER_API_KEY", raising=False)
    monkeypatch.delenv("TWITTER_API_SECRET", raising=False)
    monkeypatch.delenv("TWITTER_ACCESS_TOKEN", raising=False)
    monkeypatch.delenv("TWITTER_ACCESS_SECRET", raising=False)


# ---------------------------------------------------------------------------
# 11.2 reply_to_tweet tests
# ---------------------------------------------------------------------------

async def test_reply_to_tweet_success(twitter_env):
    """Successful reply returns the reply URL."""
    mock_response = type("Response", (), {"data": {"id": "789"}})()
    mock_user = type("User", (), {"data": type("Data", (), {"username": "testuser"})()})()

    with patch("tweepy.Client") as MockClient:
        instance = MockClient.return_value
        instance.create_tweet.return_value = mock_response
        instance.get_me.return_value = mock_user

        from mcp_server import reply_to_tweet
        result = await reply_to_tweet("123", "Great tweet!")

    assert "https://x.com/testuser/status/789" in result
    instance.create_tweet.assert_called_once_with(text="Great tweet!", in_reply_to_tweet_id="123")


async def test_reply_to_tweet_nonexistent_tweet(twitter_env):
    """Replying to a non-existent tweet returns the Twitter API error."""
    with patch("tweepy.Client") as MockClient:
        instance = MockClient.return_value
        instance.create_tweet.side_effect = Exception("404 Not Found: tweet not found")

        from mcp_server import reply_to_tweet
        result = await reply_to_tweet("999999", "Reply")

    assert "Error" in result
    assert "404" in result or "not found" in result.lower()


async def test_reply_to_tweet_too_long(twitter_env):
    """Reply exceeding 280 characters is rejected."""
    from mcp_server import reply_to_tweet
    result = await reply_to_tweet("123", "a" * 281)
    assert "Error" in result
    assert "280 character limit" in result


async def test_reply_to_tweet_no_credentials(no_twitter_env):
    """Missing credentials returns error."""
    from mcp_server import reply_to_tweet
    result = await reply_to_tweet("123", "Hello")
    assert "credentials not configured" in result.lower()


# ---------------------------------------------------------------------------
# 11.3 like_tweet tests
# ---------------------------------------------------------------------------

async def test_like_tweet_success(twitter_env):
    """Successful like returns confirmation."""
    with patch("tweepy.Client") as MockClient:
        instance = MockClient.return_value
        instance.like.return_value = None

        from mcp_server import like_tweet
        result = await like_tweet("456")

    assert "Liked tweet 456" in result


async def test_like_tweet_already_liked(twitter_env):
    """Liking an already-liked tweet succeeds (Twitter is idempotent)."""
    with patch("tweepy.Client") as MockClient:
        instance = MockClient.return_value
        instance.like.return_value = None  # idempotent success

        from mcp_server import like_tweet
        result = await like_tweet("456")

    assert "Liked tweet 456" in result


async def test_like_tweet_no_credentials(no_twitter_env):
    """Missing credentials returns error."""
    from mcp_server import like_tweet
    result = await like_tweet("456")
    assert "credentials not configured" in result.lower()


# ---------------------------------------------------------------------------
# 11.4 retweet tests
# ---------------------------------------------------------------------------

async def test_retweet_success(twitter_env):
    """Successful retweet returns confirmation."""
    with patch("tweepy.Client") as MockClient:
        instance = MockClient.return_value
        instance.retweet.return_value = None

        from mcp_server import retweet
        result = await retweet("456")

    assert "Retweeted tweet 456" in result


async def test_retweet_already_retweeted(twitter_env):
    """Retweeting an already-retweeted tweet returns the Twitter API error."""
    with patch("tweepy.Client") as MockClient:
        instance = MockClient.return_value
        instance.retweet.side_effect = Exception("You have already retweeted this Tweet")

        from mcp_server import retweet
        result = await retweet("456")

    assert "Error" in result
    assert "already retweeted" in result.lower()


async def test_retweet_no_credentials(no_twitter_env):
    """Missing credentials returns error."""
    from mcp_server import retweet
    result = await retweet("456")
    assert "credentials not configured" in result.lower()


# ---------------------------------------------------------------------------
# 11.5 get_tweet_metrics tests
# ---------------------------------------------------------------------------

async def test_get_tweet_metrics_own_recent(twitter_env):
    """Own recent tweet returns all metric categories."""
    mock_tweet = MagicMock()
    mock_tweet.id = 111
    mock_tweet.text = "Hello world"
    mock_tweet.created_at = datetime(2026, 4, 26, 12, 0, tzinfo=timezone.utc)
    mock_tweet.public_metrics = {"like_count": 10, "retweet_count": 5}
    mock_tweet.non_public_metrics = {"url_link_clicks": 3}
    mock_tweet.organic_metrics = {"impressions": 100}
    mock_response = MagicMock()
    mock_response.data = mock_tweet

    with patch("tweepy.Client") as MockClient:
        instance = MockClient.return_value
        instance.get_tweet.return_value = mock_response

        from mcp_server import get_tweet_metrics
        result = json.loads(await get_tweet_metrics("111"))

    assert result["public_metrics"]["like_count"] == 10
    assert "non_public_metrics" in result
    assert "organic_metrics" in result


async def test_get_tweet_metrics_public_only(twitter_env):
    """Other user's tweet returns only public metrics."""
    mock_tweet = MagicMock()
    mock_tweet.id = 222
    mock_tweet.text = "Someone else's tweet"
    mock_tweet.created_at = datetime(2026, 4, 26, 12, 0, tzinfo=timezone.utc)
    mock_tweet.public_metrics = {"like_count": 50}
    mock_tweet.non_public_metrics = None
    mock_tweet.organic_metrics = None
    mock_response = MagicMock()
    mock_response.data = mock_tweet

    with patch("tweepy.Client") as MockClient:
        instance = MockClient.return_value
        instance.get_tweet.return_value = mock_response

        from mcp_server import get_tweet_metrics
        result = json.loads(await get_tweet_metrics("222"))

    assert "public_metrics" in result
    assert "non_public_metrics" not in result
    assert "organic_metrics" not in result


async def test_get_tweet_metrics_not_found(twitter_env):
    """Non-existent tweet returns error."""
    mock_response = MagicMock()
    mock_response.data = None

    with patch("tweepy.Client") as MockClient:
        instance = MockClient.return_value
        instance.get_tweet.return_value = mock_response

        from mcp_server import get_tweet_metrics
        result = json.loads(await get_tweet_metrics("999999"))

    assert "error" in result
    assert "not found" in result["error"].lower()


async def test_get_tweet_metrics_no_credentials(no_twitter_env):
    """Missing credentials returns error."""
    from mcp_server import get_tweet_metrics
    result = json.loads(await get_tweet_metrics("111"))
    assert "error" in result
    assert "credentials" in result["error"].lower()


# ---------------------------------------------------------------------------
# 11.6 get_my_recent_tweets tests
# ---------------------------------------------------------------------------

async def test_get_my_recent_tweets_success(twitter_env):
    """Returns tweets with metrics."""
    mock_me = MagicMock()
    mock_me.data = type("Data", (), {"id": "99", "username": "me"})()

    mock_tweet = MagicMock()
    mock_tweet.id = 333
    mock_tweet.text = "My tweet"
    mock_tweet.created_at = datetime(2026, 4, 26, 12, 0, tzinfo=timezone.utc)
    mock_tweet.public_metrics = {"like_count": 5}
    mock_tweet.non_public_metrics = None
    mock_tweet.organic_metrics = None

    mock_timeline = MagicMock()
    mock_timeline.data = [mock_tweet]

    with patch("tweepy.Client") as MockClient:
        instance = MockClient.return_value
        instance.get_me.return_value = mock_me
        instance.get_users_tweets.return_value = mock_timeline

        from mcp_server import get_my_recent_tweets
        result = json.loads(await get_my_recent_tweets())

    assert len(result) == 1
    assert result[0]["tweet_id"] == "333"


async def test_get_my_recent_tweets_custom_limit(twitter_env):
    """Custom max_results is passed through to the API."""
    mock_me = MagicMock()
    mock_me.data = type("Data", (), {"id": "99", "username": "me"})()

    mock_timeline = MagicMock()
    mock_timeline.data = []

    with patch("tweepy.Client") as MockClient:
        instance = MockClient.return_value
        instance.get_me.return_value = mock_me
        instance.get_users_tweets.return_value = mock_timeline

        from mcp_server import get_my_recent_tweets
        await get_my_recent_tweets(max_results=5)

    # Verify the clamped value (min 5) was passed
    call_args = instance.get_users_tweets.call_args
    assert call_args.kwargs.get("max_results", call_args[1].get("max_results")) == 5


async def test_get_my_recent_tweets_empty(twitter_env):
    """Empty timeline returns empty array."""
    mock_me = MagicMock()
    mock_me.data = type("Data", (), {"id": "99", "username": "me"})()

    mock_timeline = MagicMock()
    mock_timeline.data = None

    with patch("tweepy.Client") as MockClient:
        instance = MockClient.return_value
        instance.get_me.return_value = mock_me
        instance.get_users_tweets.return_value = mock_timeline

        from mcp_server import get_my_recent_tweets
        result = json.loads(await get_my_recent_tweets())

    assert result == []


async def test_get_my_recent_tweets_no_credentials(no_twitter_env):
    """Missing credentials returns error."""
    from mcp_server import get_my_recent_tweets
    result = json.loads(await get_my_recent_tweets())
    assert "error" in result
    assert "credentials" in result["error"].lower()


# ---------------------------------------------------------------------------
# 11.7 search_tweets tests
# ---------------------------------------------------------------------------

async def test_search_tweets_results(twitter_env):
    """Search returns tweets with author info."""
    mock_tweet = MagicMock()
    mock_tweet.id = 444
    mock_tweet.text = "Kubernetes is great"
    mock_tweet.created_at = datetime(2026, 4, 26, 12, 0, tzinfo=timezone.utc)
    mock_tweet.author_id = 55
    mock_tweet.public_metrics = {"like_count": 20}

    mock_user = MagicMock()
    mock_user.id = 55
    mock_user.username = "k8sfan"

    mock_response = MagicMock()
    mock_response.data = [mock_tweet]
    mock_response.includes = {"users": [mock_user]}

    with patch("tweepy.Client") as MockClient:
        instance = MockClient.return_value
        instance.search_recent_tweets.return_value = mock_response

        from mcp_server import search_tweets
        result = json.loads(await search_tweets("kubernetes"))

    assert len(result) == 1
    assert result[0]["author_username"] == "k8sfan"


async def test_search_tweets_no_results(twitter_env):
    """No results returns empty array."""
    mock_response = MagicMock()
    mock_response.data = None
    mock_response.includes = None

    with patch("tweepy.Client") as MockClient:
        instance = MockClient.return_value
        instance.search_recent_tweets.return_value = mock_response

        from mcp_server import search_tweets
        result = json.loads(await search_tweets("zzzznonexistent"))

    assert result == []


async def test_search_tweets_403_tier_error(twitter_env):
    """403 error returns tier requirement message."""
    import tweepy

    with patch("tweepy.Client") as MockClient:
        instance = MockClient.return_value
        instance.search_recent_tweets.side_effect = tweepy.Forbidden(
            MagicMock(status_code=403)
        )

        from mcp_server import search_tweets
        result = json.loads(await search_tweets("test"))

    assert "error" in result
    assert "basic tier" in result["error"].lower()


async def test_search_tweets_no_credentials(no_twitter_env):
    """Missing credentials returns error."""
    from mcp_server import search_tweets
    result = json.loads(await search_tweets("test"))
    assert "error" in result
    assert "credentials" in result["error"].lower()


# ---------------------------------------------------------------------------
# 11.8 TwitterPlatform method tests
# ---------------------------------------------------------------------------

async def test_twitter_platform_reply():
    """reply() calls create_tweet with in_reply_to_tweet_id."""
    from platforms.twitter import TwitterPlatform

    platform = TwitterPlatform()
    mock_response = type("Response", (), {"data": {"id": "789"}})()
    mock_user = type("User", (), {"data": type("Data", (), {"username": "me"})()})()

    with patch("tweepy.Client") as MockClient:
        instance = MockClient.return_value
        instance.create_tweet.return_value = mock_response
        instance.get_me.return_value = mock_user

        result = await platform.reply("123", "Reply text", credentials={
            "api_key": "k", "api_secret": "s", "access_token": "t", "access_secret": "a",
        })

    assert result.success
    assert "789" in result.url
    instance.create_tweet.assert_called_once_with(text="Reply text", in_reply_to_tweet_id="123")


async def test_twitter_platform_like():
    """like() calls client.like()."""
    from platforms.twitter import TwitterPlatform

    platform = TwitterPlatform()

    with patch("tweepy.Client") as MockClient:
        instance = MockClient.return_value
        instance.like.return_value = None

        result = await platform.like("123", credentials={
            "api_key": "k", "api_secret": "s", "access_token": "t", "access_secret": "a",
        })

    assert result is True
    instance.like.assert_called_once_with(tweet_id="123")


async def test_twitter_platform_retweet():
    """retweet() calls client.retweet()."""
    from platforms.twitter import TwitterPlatform

    platform = TwitterPlatform()

    with patch("tweepy.Client") as MockClient:
        instance = MockClient.return_value
        instance.retweet.return_value = None

        result = await platform.retweet("123", credentials={
            "api_key": "k", "api_secret": "s", "access_token": "t", "access_secret": "a",
        })

    assert result is True
    instance.retweet.assert_called_once_with(tweet_id="123")


async def test_twitter_platform_get_metrics():
    """get_metrics() returns dict with available metrics."""
    from platforms.twitter import TwitterPlatform

    platform = TwitterPlatform()
    mock_tweet = MagicMock()
    mock_tweet.id = 111
    mock_tweet.text = "Hello"
    mock_tweet.created_at = datetime(2026, 4, 26, 12, 0, tzinfo=timezone.utc)
    mock_tweet.public_metrics = {"like_count": 5}
    mock_tweet.non_public_metrics = None
    mock_tweet.organic_metrics = None
    mock_response = MagicMock()
    mock_response.data = mock_tweet

    with patch("tweepy.Client") as MockClient:
        instance = MockClient.return_value
        instance.get_tweet.return_value = mock_response

        result = await platform.get_metrics("111", credentials={
            "api_key": "k", "api_secret": "s", "access_token": "t", "access_secret": "a",
        })

    assert result["tweet_id"] == "111"
    assert "public_metrics" in result


async def test_twitter_platform_get_my_tweets():
    """get_my_tweets() returns list of tweet dicts."""
    from platforms.twitter import TwitterPlatform

    platform = TwitterPlatform()
    mock_me = MagicMock()
    mock_me.data = type("Data", (), {"id": "99"})()

    mock_tweet = MagicMock()
    mock_tweet.id = 333
    mock_tweet.text = "My tweet"
    mock_tweet.created_at = datetime(2026, 4, 26, 12, 0, tzinfo=timezone.utc)
    mock_tweet.public_metrics = {"like_count": 5}
    mock_tweet.non_public_metrics = None
    mock_tweet.organic_metrics = None

    mock_timeline = MagicMock()
    mock_timeline.data = [mock_tweet]

    with patch("tweepy.Client") as MockClient:
        instance = MockClient.return_value
        instance.get_me.return_value = mock_me
        instance.get_users_tweets.return_value = mock_timeline

        result = await platform.get_my_tweets(10, credentials={
            "api_key": "k", "api_secret": "s", "access_token": "t", "access_secret": "a",
        })

    assert len(result) == 1
    assert result[0]["tweet_id"] == "333"


async def test_twitter_platform_search():
    """search() returns tweets with author usernames."""
    from platforms.twitter import TwitterPlatform

    platform = TwitterPlatform()
    mock_tweet = MagicMock()
    mock_tweet.id = 444
    mock_tweet.text = "Search result"
    mock_tweet.created_at = datetime(2026, 4, 26, 12, 0, tzinfo=timezone.utc)
    mock_tweet.author_id = 55
    mock_tweet.public_metrics = {"like_count": 20}

    mock_user = MagicMock()
    mock_user.id = 55
    mock_user.username = "author1"

    mock_response = MagicMock()
    mock_response.data = [mock_tweet]
    mock_response.includes = {"users": [mock_user]}

    with patch("tweepy.Client") as MockClient:
        instance = MockClient.return_value
        instance.search_recent_tweets.return_value = mock_response

        result = await platform.search("query", credentials={
            "api_key": "k", "api_secret": "s", "access_token": "t", "access_secret": "a",
        }, max_results=10)

    assert len(result) == 1
    assert result[0]["author_username"] == "author1"
