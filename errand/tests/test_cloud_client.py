"""Tests for cloud WebSocket client."""
import asyncio
import json
import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from cloud_client import CloudWebSocketClient, _run_token_refresh_loop


class TestMessageHandling:
    @pytest.mark.asyncio
    async def test_ping_responds_with_pong(self):
        client = CloudWebSocketClient()
        ws = AsyncMock()

        await client._handle_message(ws, {"type": "ping", "ts": 1234567890})

        ws.send.assert_called_once()
        sent = json.loads(ws.send.call_args[0][0])
        assert sent["type"] == "pong"
        assert sent["ts"] == 1234567890

    @pytest.mark.asyncio
    async def test_webhook_dispatches_and_acks(self):
        client = CloudWebSocketClient()
        ws = AsyncMock()

        with patch("cloud_dispatch.dispatch_cloud_webhook", new_callable=AsyncMock) as mock_dispatch:
            await client._handle_message(ws, {
                "type": "webhook",
                "id": "msg-123",
                "integration": "slack",
                "endpoint_type": "events",
                "body": '{"test": true}',
            })

        mock_dispatch.assert_called_once()
        ws.send.assert_called_once()
        sent = json.loads(ws.send.call_args[0][0])
        assert sent["type"] == "ack"
        assert sent["id"] == "msg-123"

    @pytest.mark.asyncio
    async def test_duplicate_message_acks_without_processing(self):
        client = CloudWebSocketClient()
        ws = AsyncMock()

        # First message — should dispatch
        with patch("cloud_dispatch.dispatch_cloud_webhook", new_callable=AsyncMock) as mock_dispatch:
            await client._handle_message(ws, {
                "type": "webhook",
                "id": "msg-dup",
                "integration": "slack",
                "endpoint_type": "events",
                "body": "{}",
            })
            assert mock_dispatch.call_count == 1

        ws.reset_mock()

        # Same ID — should ACK but not dispatch
        with patch("cloud_dispatch.dispatch_cloud_webhook", new_callable=AsyncMock) as mock_dispatch:
            await client._handle_message(ws, {
                "type": "webhook",
                "id": "msg-dup",
                "integration": "slack",
                "endpoint_type": "events",
                "body": "{}",
            })
            mock_dispatch.assert_not_called()

        # Should still ACK
        ws.send.assert_called_once()
        sent = json.loads(ws.send.call_args[0][0])
        assert sent["type"] == "ack"
        assert sent["id"] == "msg-dup"


class TestReconnection:
    def test_backoff_first_attempt_is_small(self):
        client = CloudWebSocketClient()
        client._backoff_attempt = 0
        delay = client._backoff_delay()
        assert 0 <= delay <= 0.5

    def test_backoff_increases_exponentially(self):
        client = CloudWebSocketClient()
        delays = []
        for i in range(6):
            client._backoff_attempt = i
            delays.append(client._backoff_delay())
        # Later delays should be larger (within jitter variance)
        assert delays[-1] > delays[0]

    def test_backoff_caps_at_30_seconds(self):
        client = CloudWebSocketClient()
        client._backoff_attempt = 100
        delay = client._backoff_delay()
        assert delay <= 30

    @pytest.mark.asyncio
    async def test_close_4001_allows_reconnect(self):
        """A single 4001 close should allow reconnection, not stop permanently."""
        client = CloudWebSocketClient()
        client._running = True
        client._backoff_attempt = 0

        await client._handle_close(4001, "superseded")

        assert client._running is True
        assert client._consecutive_evictions == 1

    @pytest.mark.asyncio
    async def test_close_4001_consecutive_exceeds_threshold_stops(self):
        """5 consecutive 4001 closes without successful handshake should stop permanently."""
        client = CloudWebSocketClient()
        client._running = True
        client._consecutive_evictions = 4  # One away from threshold

        await client._handle_close(4001, "superseded")

        assert client._running is False
        assert client._consecutive_evictions == 5

    @pytest.mark.asyncio
    async def test_close_4003_stops_reconnect(self):
        client = CloudWebSocketClient()
        client._running = True

        with patch.object(client, "_set_credential_status", new_callable=AsyncMock):
            await client._handle_close(4003, "disabled")

        assert client._running is False

    @pytest.mark.asyncio
    async def test_close_4002_attempts_refresh(self):
        client = CloudWebSocketClient()
        client._running = True

        with patch.object(client, "_try_refresh_token", new_callable=AsyncMock, return_value=True) as mock_refresh:
            await client._handle_close(4002, "auth_expired")

        mock_refresh.assert_called_once()
        assert client._running is True  # Should keep running if refresh succeeds

    @pytest.mark.asyncio
    async def test_close_4002_stops_if_refresh_fails(self):
        client = CloudWebSocketClient()
        client._running = True

        with patch.object(client, "_try_refresh_token", new_callable=AsyncMock, return_value=False), \
             patch.object(client, "_set_credential_status", new_callable=AsyncMock):
            await client._handle_close(4002, "auth_expired")

        assert client._running is False

    @pytest.mark.asyncio
    async def test_successful_handshake_resets_eviction_counter(self):
        """Consecutive eviction counter should reset to 0 after a successful register/registered handshake."""
        client = CloudWebSocketClient()
        client._running = True
        client._consecutive_evictions = 3

        ws = AsyncMock()

        def stop_after_one(*args, **kwargs):
            """Return one message then stop the client to exit the loop."""
            client._running = False
            return json.dumps({"type": "ping", "ts": 1})

        ws.recv = AsyncMock(side_effect=stop_after_one)

        ws_ctx = AsyncMock()
        ws_ctx.__aenter__ = AsyncMock(return_value=ws)
        ws_ctx.__aexit__ = AsyncMock(return_value=False)

        with patch("cloud_client.websockets.connect", return_value=ws_ctx), \
             patch.object(client, "_load_credentials", new_callable=AsyncMock, return_value={"access_token": "tok"}), \
             patch.object(client, "_get_cloud_ws_url", new_callable=AsyncMock, return_value="wss://cloud/ws"), \
             patch.object(client, "_send_register", new_callable=AsyncMock), \
             patch.object(client, "_wait_for_registered", new_callable=AsyncMock, return_value=True), \
             patch.object(client, "_cleanup_subscriptions", new_callable=AsyncMock), \
             patch("cloud_client.publish_event", new_callable=AsyncMock):
            await client._connect_and_receive()

        assert client._consecutive_evictions == 0

    @pytest.mark.asyncio
    async def test_liveness_watchdog_closes_on_timeout(self):
        """Connection should be closed and reconnect triggered when no messages received within 90s."""
        client = CloudWebSocketClient()
        client._running = True

        ws = AsyncMock()
        # recv blocks indefinitely → triggers TimeoutError from wait_for
        ws.recv = AsyncMock(side_effect=asyncio.TimeoutError())
        ws.close = AsyncMock()

        # Mock the context manager for websockets.connect
        ws_ctx = AsyncMock()
        ws_ctx.__aenter__ = AsyncMock(return_value=ws)
        ws_ctx.__aexit__ = AsyncMock(return_value=False)

        with patch("cloud_client.websockets.connect", return_value=ws_ctx), \
             patch.object(client, "_load_credentials", new_callable=AsyncMock, return_value={"access_token": "tok"}), \
             patch.object(client, "_get_cloud_ws_url", new_callable=AsyncMock, return_value="wss://cloud/ws"), \
             patch.object(client, "_send_register", new_callable=AsyncMock), \
             patch.object(client, "_wait_for_registered", new_callable=AsyncMock, return_value=True), \
             patch.object(client, "_cleanup_subscriptions", new_callable=AsyncMock), \
             patch("cloud_client.publish_event", new_callable=AsyncMock):
            await client._connect_and_receive()

        ws.close.assert_called_once()
        # Client should still be running (reconnect, not permanent stop)
        assert client._running is True

    @pytest.mark.asyncio
    async def test_status_cleared_immediately_after_connection_drop(self):
        """_ws_connected should be False and cloud_status: disconnected published before backoff."""
        import cloud_client as cc

        client = CloudWebSocketClient()
        client._running = True

        events_published = []
        call_order = []

        async def track_publish(event_type, data):
            events_published.append((event_type, data))
            call_order.append("publish")

        async def track_sleep(secs):
            call_order.append("sleep")
            # Stop after first reconnect attempt
            client._running = False

        # Make _connect_and_receive raise to simulate a connection drop
        with patch.object(client, "_connect_and_receive", new_callable=AsyncMock, side_effect=Exception("connection lost")), \
             patch("cloud_client.publish_event", side_effect=track_publish), \
             patch("asyncio.sleep", side_effect=track_sleep):
            original_ws_connected = cc._ws_connected
            cc._ws_connected = True
            await client.run()

        # Verify _ws_connected is False
        assert cc._ws_connected is False
        # Verify disconnected was published before sleep
        assert "publish" in call_order
        assert "sleep" in call_order
        assert call_order.index("publish") < call_order.index("sleep")
        # Verify the event content
        assert any(e[0] == "cloud_status" and e[1]["status"] == "disconnected" for e in events_published)


class TestTokenRefresh:
    @pytest.mark.asyncio
    async def test_refresh_loop_triggers_when_token_near_expiry(self):
        """Token refresh loop should call _try_refresh_token when token is near expiry."""
        mock_cred = MagicMock()
        mock_cred.status = "connected"
        # Token expires in 30 seconds (within the 60s threshold)
        mock_cred.encrypted_data = "encrypted"

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_cred

        mock_session = AsyncMock()
        mock_session.execute = AsyncMock(return_value=mock_result)

        cred_data = {"access_token": "test", "refresh_token": "rt", "token_expiry": time.time() + 30}

        call_count = 0

        async def fake_sleep(secs):
            nonlocal call_count
            call_count += 1
            if call_count > 1:
                raise asyncio.CancelledError()

        with patch("cloud_client.async_session") as mock_session_maker, \
             patch("cloud_client.decrypt_credentials", return_value=cred_data), \
             patch.object(CloudWebSocketClient, "_try_refresh_token", new_callable=AsyncMock, return_value=True) as mock_refresh, \
             patch("asyncio.sleep", side_effect=fake_sleep):
            mock_session_maker.return_value.__aenter__ = AsyncMock(return_value=mock_session)
            mock_session_maker.return_value.__aexit__ = AsyncMock(return_value=False)

            await _run_token_refresh_loop()

        mock_refresh.assert_called_once()

    @pytest.mark.asyncio
    async def test_refresh_loop_skips_when_token_not_near_expiry(self):
        """Token refresh loop should not refresh when token has plenty of time left."""
        mock_cred = MagicMock()
        mock_cred.status = "connected"
        mock_cred.encrypted_data = "encrypted"

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_cred

        mock_session = AsyncMock()
        mock_session.execute = AsyncMock(return_value=mock_result)

        # Token expires in 5 minutes (well beyond the 60s threshold)
        cred_data = {"access_token": "test", "refresh_token": "rt", "token_expiry": time.time() + 300}

        call_count = 0

        async def fake_sleep(secs):
            nonlocal call_count
            call_count += 1
            if call_count > 1:
                raise asyncio.CancelledError()

        with patch("cloud_client.async_session") as mock_session_maker, \
             patch("cloud_client.decrypt_credentials", return_value=cred_data), \
             patch.object(CloudWebSocketClient, "_try_refresh_token", new_callable=AsyncMock) as mock_refresh, \
             patch("asyncio.sleep", side_effect=fake_sleep):
            mock_session_maker.return_value.__aenter__ = AsyncMock(return_value=mock_session)
            mock_session_maker.return_value.__aexit__ = AsyncMock(return_value=False)

            await _run_token_refresh_loop()

        mock_refresh.assert_not_called()

    @pytest.mark.asyncio
    async def test_refresh_loop_publishes_error_on_failure(self):
        """Token refresh loop should publish error event when refresh fails."""
        mock_cred = MagicMock()
        mock_cred.status = "connected"
        mock_cred.encrypted_data = "encrypted"

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_cred

        mock_session = AsyncMock()
        mock_session.execute = AsyncMock(return_value=mock_result)

        cred_data = {"access_token": "test", "refresh_token": "rt", "token_expiry": time.time() + 30}

        call_count = 0

        async def fake_sleep(secs):
            nonlocal call_count
            call_count += 1
            if call_count > 1:
                raise asyncio.CancelledError()

        with patch("cloud_client.async_session") as mock_session_maker, \
             patch("cloud_client.decrypt_credentials", return_value=cred_data), \
             patch.object(CloudWebSocketClient, "_try_refresh_token", new_callable=AsyncMock, return_value=False), \
             patch("cloud_client.publish_event", new_callable=AsyncMock) as mock_publish, \
             patch("asyncio.sleep", side_effect=fake_sleep):
            mock_session_maker.return_value.__aenter__ = AsyncMock(return_value=mock_session)
            mock_session_maker.return_value.__aexit__ = AsyncMock(return_value=False)

            await _run_token_refresh_loop()

        mock_publish.assert_called_once()
        call_args = mock_publish.call_args[0]
        assert call_args[0] == "cloud_status"
        assert call_args[1]["status"] == "error"
