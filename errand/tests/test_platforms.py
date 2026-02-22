"""Tests for PlatformRegistry and TwitterPlatform."""
from unittest.mock import MagicMock, patch

import pytest

from platforms import PlatformRegistry
from platforms.base import Platform, PlatformCapability, PlatformInfo
from platforms.twitter import TwitterPlatform


# --- PlatformRegistry tests (Task 3.3) ---


class FakePlatform(Platform):
    def __init__(self, platform_id: str = "fake", label: str = "Fake"):
        self._id = platform_id
        self._label = label

    def info(self) -> PlatformInfo:
        return PlatformInfo(
            id=self._id,
            label=self._label,
            capabilities={PlatformCapability.POST},
            credential_schema=[],
        )

    async def verify_credentials(self, credentials: dict) -> bool:
        return True


def test_registry_register_and_get():
    registry = PlatformRegistry()
    platform = FakePlatform("test", "Test Platform")
    registry.register(platform)
    assert registry.get("test") is platform


def test_registry_get_missing():
    registry = PlatformRegistry()
    assert registry.get("nonexistent") is None


def test_registry_list_all():
    registry = PlatformRegistry()
    registry.register(FakePlatform("alpha", "Alpha"))
    registry.register(FakePlatform("beta", "Beta"))
    infos = registry.list_all()
    ids = {info.id for info in infos}
    assert ids == {"alpha", "beta"}


def test_registry_list_all_empty():
    registry = PlatformRegistry()
    assert registry.list_all() == []


def test_registry_register_overwrites_same_id():
    registry = PlatformRegistry()
    p1 = FakePlatform("dup", "First")
    p2 = FakePlatform("dup", "Second")
    registry.register(p1)
    registry.register(p2)
    assert registry.get("dup") is p2
    assert len(registry.list_all()) == 1


# --- TwitterPlatform tests (Task 5.5) ---


def test_twitter_info():
    twitter = TwitterPlatform()
    info = twitter.info()
    assert info.id == "twitter"
    assert info.label == "Twitter/X"
    assert PlatformCapability.POST in info.capabilities
    assert PlatformCapability.MEDIA in info.capabilities
    schema_keys = [f["key"] for f in info.credential_schema]
    assert schema_keys == ["api_key", "api_secret", "access_token", "access_secret"]
    # Verify schema field structure
    for field in info.credential_schema:
        assert "type" in field
        assert "required" in field


@pytest.mark.asyncio
async def test_twitter_verify_credentials_success():
    twitter = TwitterPlatform()
    mock_user = MagicMock()
    mock_user.data = MagicMock()

    with patch("tweepy.Client") as MockClient:
        MockClient.return_value.get_me.return_value = mock_user
        result = await twitter.verify_credentials({
            "api_key": "k",
            "api_secret": "s",
            "access_token": "t",
            "access_secret": "a",
        })

    assert result is True


@pytest.mark.asyncio
async def test_twitter_verify_credentials_failure():
    twitter = TwitterPlatform()

    with patch("tweepy.Client") as MockClient:
        MockClient.return_value.get_me.side_effect = Exception("401 Unauthorized")
        result = await twitter.verify_credentials({
            "api_key": "k",
            "api_secret": "s",
            "access_token": "t",
            "access_secret": "a",
        })

    assert result is False


@pytest.mark.asyncio
async def test_twitter_post_success():
    twitter = TwitterPlatform()
    mock_response = MagicMock()
    mock_response.data = {"id": "99999"}
    mock_user = MagicMock()
    mock_user.data.username = "testbot"

    with patch("tweepy.Client") as MockClient:
        instance = MockClient.return_value
        instance.create_tweet.return_value = mock_response
        instance.get_me.return_value = mock_user

        result = await twitter.post(
            "Hello!",
            credentials={
                "api_key": "k",
                "api_secret": "s",
                "access_token": "t",
                "access_secret": "a",
            },
        )

    assert result.success is True
    assert result.url == "https://x.com/testbot/status/99999"
    instance.create_tweet.assert_called_once_with(text="Hello!")


@pytest.mark.asyncio
async def test_twitter_post_no_credentials():
    twitter = TwitterPlatform()
    result = await twitter.post("Hello!")
    assert result.success is False
    assert "No credentials" in result.error


@pytest.mark.asyncio
async def test_twitter_post_api_error():
    twitter = TwitterPlatform()

    with patch("tweepy.Client") as MockClient:
        MockClient.return_value.create_tweet.side_effect = Exception("Rate limited")

        result = await twitter.post(
            "Hello!",
            credentials={
                "api_key": "k",
                "api_secret": "s",
                "access_token": "t",
                "access_secret": "a",
            },
        )

    assert result.success is False
    assert "Rate limited" in result.error
