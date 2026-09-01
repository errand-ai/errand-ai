"""Tests for cloud auth module (device grant and token refresh via errand-cloud)."""
from unittest.mock import AsyncMock, patch, MagicMock

import httpx
import pytest

from cloud_auth import (
    DEVICE_DEFAULT_INTERVAL,
    DEVICE_DENIED,
    DEVICE_ERROR,
    DEVICE_EXPIRED,
    DEVICE_PENDING,
    DEVICE_SLOW_DOWN,
    DEVICE_TOKENS,
    DeviceTokenResult,
    poll_device_token,
    poll_until_complete,
    refresh_token,
    request_device_code,
)


class TestRefreshToken:
    @pytest.mark.asyncio
    async def test_refreshes_token(self):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "access_token": "new-at",
            "refresh_token": "new-rt",
            "expires_in": 300,
            "token_type": "Bearer",
        }
        mock_response.raise_for_status = MagicMock()

        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("cloud_auth.httpx.AsyncClient", return_value=mock_client):
            tokens = await refresh_token("https://cloud.test", "old-rt")

        assert tokens["access_token"] == "new-at"
        mock_client.post.assert_called_once_with(
            "https://cloud.test/auth/tenant/refresh",
            json={"refresh_token": "old-rt"},
        )

    @pytest.mark.asyncio
    async def test_raises_on_failure(self):
        mock_response = MagicMock()
        mock_response.raise_for_status.side_effect = Exception("401 Unauthorized")

        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("cloud_auth.httpx.AsyncClient", return_value=mock_client):
            with pytest.raises(Exception, match="401"):
                await refresh_token("https://cloud.test", "expired-rt")


class TestRequestDeviceCode:
    @pytest.mark.asyncio
    async def test_returns_display_fields(self):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "device_code": "dc-secret",
            "user_code": "JHBW-PMHF",
            "verification_uri": "https://cloud.test/auth/tenant/device",
            "verification_uri_complete": "https://cloud.test/auth/tenant/device?user_code=JHBW-PMHF",
            "expires_in": 600,
            "interval": 5,
        }
        mock_response.raise_for_status = MagicMock()

        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("cloud_auth.httpx.AsyncClient", return_value=mock_client):
            grant = await request_device_code("https://cloud.test")

        assert grant["user_code"] == "JHBW-PMHF"
        assert grant["verification_uri"] == "https://cloud.test/auth/tenant/device"
        assert grant["verification_uri_complete"].endswith("user_code=JHBW-PMHF")
        assert grant["expires_in"] == 600
        assert grant["interval"] == 5
        mock_client.post.assert_called_once_with(
            "https://cloud.test/auth/tenant/device/code",
            json={},
        )

    @pytest.mark.asyncio
    async def test_sends_no_callback_parameter(self):
        """The whole point of the device grant: nothing that could be substituted."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"device_code": "dc", "user_code": "AAAA-BBBB"}
        mock_response.raise_for_status = MagicMock()

        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("cloud_auth.httpx.AsyncClient", return_value=mock_client):
            await request_device_code("https://cloud.test")

        url = mock_client.post.call_args[0][0]
        payload = mock_client.post.call_args[1]["json"]
        assert "redirect_uri" not in url
        assert "redirect_uri" not in payload
        assert payload == {}

    @pytest.mark.asyncio
    async def test_raises_on_failure(self):
        mock_response = MagicMock()
        mock_response.raise_for_status.side_effect = Exception("429 Too Many Requests")

        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("cloud_auth.httpx.AsyncClient", return_value=mock_client):
            with pytest.raises(Exception, match="429"):
                await request_device_code("https://cloud.test")


def _token_client(status_code: int, payload: dict):
    mock_response = MagicMock()
    mock_response.status_code = status_code
    mock_response.json.return_value = payload

    mock_client = AsyncMock()
    mock_client.post = AsyncMock(return_value=mock_response)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    return mock_client


class TestPollDeviceToken:
    @pytest.mark.asyncio
    async def test_200_yields_tokens(self):
        mock_client = _token_client(200, {
            "access_token": "at-123",
            "refresh_token": "rt-123",
            "expires_in": 300,
            "token_type": "Bearer",
        })

        with patch("cloud_auth.httpx.AsyncClient", return_value=mock_client):
            result = await poll_device_token("https://cloud.test", "dc-secret")

        assert result.outcome == DEVICE_TOKENS
        assert result.tokens["access_token"] == "at-123"
        mock_client.post.assert_called_once_with(
            "https://cloud.test/auth/tenant/device/token",
            json={"device_code": "dc-secret"},
        )

    @pytest.mark.asyncio
    @pytest.mark.parametrize("error_code,expected", [
        ("authorization_pending", DEVICE_PENDING),
        ("slow_down", DEVICE_SLOW_DOWN),
        ("access_denied", DEVICE_DENIED),
        ("expired_token", DEVICE_EXPIRED),
    ])
    async def test_error_codes_map_to_distinct_outcomes(self, error_code, expected):
        mock_client = _token_client(400, {"error": error_code, "error_description": "d"})

        with patch("cloud_auth.httpx.AsyncClient", return_value=mock_client):
            result = await poll_device_token("https://cloud.test", "dc-secret")

        assert result.outcome == expected
        assert result.tokens is None

    @pytest.mark.asyncio
    async def test_outcomes_are_all_distinct(self):
        assert len({
            DEVICE_TOKENS, DEVICE_PENDING, DEVICE_SLOW_DOWN,
            DEVICE_DENIED, DEVICE_EXPIRED, DEVICE_ERROR,
        }) == 6

    @pytest.mark.asyncio
    async def test_rate_limit_is_an_error_not_a_retry(self):
        """A 429 must not look like `authorization_pending`, which would tighten the loop."""
        mock_client = _token_client(429, {"detail": "Too many requests"})

        with patch("cloud_auth.httpx.AsyncClient", return_value=mock_client):
            result = await poll_device_token("https://cloud.test", "dc-secret")

        assert result.outcome == DEVICE_ERROR
        assert "rate" in result.detail.lower() or "429" in result.detail

    @pytest.mark.asyncio
    async def test_unknown_error_code_is_an_error(self):
        mock_client = _token_client(400, {"error": "something_new"})

        with patch("cloud_auth.httpx.AsyncClient", return_value=mock_client):
            result = await poll_device_token("https://cloud.test", "dc-secret")

        assert result.outcome == DEVICE_ERROR
        assert "something_new" in result.detail

    @pytest.mark.asyncio
    async def test_transport_failure_is_an_error(self):
        mock_client = AsyncMock()
        mock_client.post = AsyncMock(side_effect=httpx.ConnectError("boom"))
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("cloud_auth.httpx.AsyncClient", return_value=mock_client):
            result = await poll_device_token("https://cloud.test", "dc-secret")

        assert result.outcome == DEVICE_ERROR


class _FakeClock:
    """Deterministic clock: sleeping advances time, so expiry is reachable."""

    def __init__(self):
        self.now = 0.0
        self.slept: list[float] = []

    async def sleep(self, seconds: float):
        self.slept.append(seconds)
        self.now += seconds

    def monotonic(self) -> float:
        return self.now


class TestPollUntilComplete:
    @pytest.mark.asyncio
    async def test_waits_the_advertised_interval(self):
        clock = _FakeClock()
        results = [
            DeviceTokenResult(outcome=DEVICE_PENDING),
            DeviceTokenResult(outcome=DEVICE_TOKENS, tokens={"access_token": "at"}),
        ]

        with patch("cloud_auth.poll_device_token", new_callable=AsyncMock, side_effect=results):
            result = await poll_until_complete(
                "https://cloud.test", "dc", interval=7, expires_in=600,
                sleep=clock.sleep, monotonic=clock.monotonic,
            )

        assert result.outcome == DEVICE_TOKENS
        assert clock.slept == [7, 7]

    @pytest.mark.asyncio
    async def test_backs_off_further_on_slow_down(self):
        clock = _FakeClock()
        results = [
            DeviceTokenResult(outcome=DEVICE_SLOW_DOWN),
            DeviceTokenResult(outcome=DEVICE_SLOW_DOWN),
            DeviceTokenResult(outcome=DEVICE_TOKENS, tokens={"access_token": "at"}),
        ]

        with patch("cloud_auth.poll_device_token", new_callable=AsyncMock, side_effect=results):
            result = await poll_until_complete(
                "https://cloud.test", "dc", interval=5, expires_in=600,
                sleep=clock.sleep, monotonic=clock.monotonic,
            )

        assert result.outcome == DEVICE_TOKENS
        assert clock.slept == [5, 10, 15]

    @pytest.mark.asyncio
    async def test_stops_on_access_denied(self):
        clock = _FakeClock()
        poll = AsyncMock(side_effect=[DeviceTokenResult(outcome=DEVICE_DENIED)])

        with patch("cloud_auth.poll_device_token", poll):
            result = await poll_until_complete(
                "https://cloud.test", "dc", interval=5, expires_in=600,
                sleep=clock.sleep, monotonic=clock.monotonic,
            )

        assert result.outcome == DEVICE_DENIED
        assert poll.await_count == 1

    @pytest.mark.asyncio
    async def test_stops_on_expired_token(self):
        clock = _FakeClock()
        poll = AsyncMock(side_effect=[DeviceTokenResult(outcome=DEVICE_EXPIRED)])

        with patch("cloud_auth.poll_device_token", poll):
            result = await poll_until_complete(
                "https://cloud.test", "dc", interval=5, expires_in=600,
                sleep=clock.sleep, monotonic=clock.monotonic,
            )

        assert result.outcome == DEVICE_EXPIRED
        assert poll.await_count == 1

    @pytest.mark.asyncio
    async def test_stops_on_error(self):
        clock = _FakeClock()
        poll = AsyncMock(side_effect=[DeviceTokenResult(outcome=DEVICE_ERROR, detail="429")])

        with patch("cloud_auth.poll_device_token", poll):
            result = await poll_until_complete(
                "https://cloud.test", "dc", interval=5, expires_in=600,
                sleep=clock.sleep, monotonic=clock.monotonic,
            )

        assert result.outcome == DEVICE_ERROR
        assert poll.await_count == 1

    @pytest.mark.asyncio
    async def test_stops_when_the_grant_expires(self):
        """The poller must not outlive the grant it is polling for."""
        clock = _FakeClock()
        poll = AsyncMock(return_value=DeviceTokenResult(outcome=DEVICE_PENDING))

        with patch("cloud_auth.poll_device_token", poll):
            result = await poll_until_complete(
                "https://cloud.test", "dc", interval=5, expires_in=20,
                sleep=clock.sleep, monotonic=clock.monotonic,
            )

        assert result.outcome == DEVICE_EXPIRED
        assert clock.now <= 25
        assert poll.await_count <= 4

    @pytest.mark.asyncio
    async def test_falls_back_to_default_interval_when_unusable(self):
        clock = _FakeClock()
        poll = AsyncMock(side_effect=[DeviceTokenResult(outcome=DEVICE_TOKENS, tokens={})])

        with patch("cloud_auth.poll_device_token", poll):
            await poll_until_complete(
                "https://cloud.test", "dc", interval=0, expires_in=600,
                sleep=clock.sleep, monotonic=clock.monotonic,
            )

        assert clock.slept == [DEVICE_DEFAULT_INTERVAL]
