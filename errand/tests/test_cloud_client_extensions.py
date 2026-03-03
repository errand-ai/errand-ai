"""Tests for cloud WebSocket client extensions (registration, proxy, subscribe)."""
import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from cloud_client import CloudWebSocketClient


# ---------------------------------------------------------------------------
# Registration tests (5.9)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_register_message_sent():
    """On connect, register message should include version and capabilities."""
    client = CloudWebSocketClient()
    ws = AsyncMock()

    async def mock_get_caps():
        return ["tasks", "settings", "mcp-servers"]

    with patch("capabilities.get_server_version", return_value="0.69.0"), \
         patch("capabilities.get_capabilities", side_effect=mock_get_caps):
        await client._send_register(ws)

    ws.send.assert_called_once()
    sent = json.loads(ws.send.call_args[0][0])
    assert sent["type"] == "register"
    assert sent["server_version"] == "0.69.0"
    assert sent["protocol_version"] == 2
    assert "tasks" in sent["capabilities"]
    assert "settings" in sent["capabilities"]


@pytest.mark.asyncio
async def test_register_waits_for_registered():
    """Client should wait for 'registered' acknowledgement."""
    client = CloudWebSocketClient()
    ws = AsyncMock()
    ws.recv = AsyncMock(return_value=json.dumps({"type": "registered", "config": {}}))

    result = await client._wait_for_registered(ws)
    assert result is True


@pytest.mark.asyncio
async def test_register_timeout_still_proceeds():
    """Client should proceed even if 'registered' times out."""
    client = CloudWebSocketClient()
    ws = AsyncMock()

    async def slow_recv():
        await asyncio.sleep(60)
        return json.dumps({"type": "registered"})

    ws.recv = slow_recv

    result = await client._wait_for_registered(ws, timeout=0.1)
    assert result is True  # Proceeds anyway


# ---------------------------------------------------------------------------
# Proxy request tests (5.10)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_proxy_request_get():
    """Proxy GET request should forward and return response."""
    client = CloudWebSocketClient()
    ws = AsyncMock()

    message = {
        "type": "proxy_request",
        "id": "req-1",
        "method": "GET",
        "path": "/api/tasks",
        "headers": {},
        "body": None,
        "jwt": "cloud-jwt-token",
    }

    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.headers = {"content-type": "application/json"}
    mock_response.text = '[{"id": "1", "title": "Test"}]'

    with patch("httpx.AsyncClient") as mock_client_class:
        mock_client = AsyncMock()
        mock_client.request = AsyncMock(return_value=mock_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client_class.return_value = mock_client

        await client._handle_proxy_request(ws, message)

    ws.send.assert_called_once()
    sent = json.loads(ws.send.call_args[0][0])
    assert sent["type"] == "proxy_response"
    assert sent["id"] == "req-1"
    assert sent["status"] == 200
    assert "Test" in sent["body"]


@pytest.mark.asyncio
async def test_proxy_request_forwards_cloud_jwt():
    """Proxy request should inject X-Cloud-JWT header."""
    client = CloudWebSocketClient()
    ws = AsyncMock()

    message = {
        "type": "proxy_request",
        "id": "req-2",
        "method": "GET",
        "path": "/api/tasks",
        "headers": {"accept": "application/json"},
        "body": None,
        "jwt": "my-cloud-jwt",
    }

    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.headers = {}
    mock_response.text = "ok"

    with patch("httpx.AsyncClient") as mock_client_class:
        mock_client = AsyncMock()
        mock_client.request = AsyncMock(return_value=mock_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client_class.return_value = mock_client

        await client._handle_proxy_request(ws, message)

    # Verify X-Cloud-JWT and X-Proxy-Secret were in the request headers
    call_kwargs = mock_client.request.call_args
    req_headers = call_kwargs.kwargs.get("headers") or call_kwargs[1].get("headers", {})
    assert req_headers.get("X-Cloud-JWT") == "my-cloud-jwt"
    assert "X-Proxy-Secret" in req_headers


@pytest.mark.asyncio
async def test_proxy_request_post_with_body():
    """Proxy POST request should forward body."""
    client = CloudWebSocketClient()
    ws = AsyncMock()

    message = {
        "type": "proxy_request",
        "id": "req-3",
        "method": "POST",
        "path": "/api/tasks",
        "headers": {"content-type": "application/json"},
        "body": '{"input": "Buy groceries"}',
        "jwt": None,
    }

    mock_response = MagicMock()
    mock_response.status_code = 201
    mock_response.headers = {"content-type": "application/json"}
    mock_response.text = '{"id": "new-1"}'

    with patch("httpx.AsyncClient") as mock_client_class:
        mock_client = AsyncMock()
        mock_client.request = AsyncMock(return_value=mock_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client_class.return_value = mock_client

        await client._handle_proxy_request(ws, message)

    sent = json.loads(ws.send.call_args[0][0])
    assert sent["status"] == 201

    # Verify body was forwarded
    call_kwargs = mock_client.request.call_args
    assert call_kwargs.kwargs.get("content") == b'{"input": "Buy groceries"}'


@pytest.mark.asyncio
async def test_proxy_request_404():
    """Proxy request to non-existent endpoint should return 404 response."""
    client = CloudWebSocketClient()
    ws = AsyncMock()

    message = {
        "type": "proxy_request",
        "id": "req-4",
        "method": "GET",
        "path": "/api/nonexistent",
        "headers": {},
        "body": None,
        "jwt": None,
    }

    mock_response = MagicMock()
    mock_response.status_code = 404
    mock_response.headers = {}
    mock_response.text = '{"detail": "Not found"}'

    with patch("httpx.AsyncClient") as mock_client_class:
        mock_client = AsyncMock()
        mock_client.request = AsyncMock(return_value=mock_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client_class.return_value = mock_client

        await client._handle_proxy_request(ws, message)

    sent = json.loads(ws.send.call_args[0][0])
    assert sent["type"] == "proxy_response"
    assert sent["id"] == "req-4"
    assert sent["status"] == 404


@pytest.mark.asyncio
async def test_proxy_request_failure_returns_502():
    """Proxy request that fails returns 502."""
    client = CloudWebSocketClient()
    ws = AsyncMock()

    message = {
        "type": "proxy_request",
        "id": "req-5",
        "method": "GET",
        "path": "/api/tasks",
        "headers": {},
        "body": None,
        "jwt": None,
    }

    with patch("httpx.AsyncClient") as mock_client_class:
        mock_client = AsyncMock()
        mock_client.request = AsyncMock(side_effect=Exception("Connection refused"))
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client_class.return_value = mock_client

        await client._handle_proxy_request(ws, message)

    sent = json.loads(ws.send.call_args[0][0])
    assert sent["type"] == "proxy_response"
    assert sent["id"] == "req-5"
    assert sent["status"] == 502


# ---------------------------------------------------------------------------
# Subscribe/unsubscribe tests (5.11)
# ---------------------------------------------------------------------------


def test_channel_mapping():
    """Channel mapping should convert cloud names to Valkey channel names."""
    client = CloudWebSocketClient()
    assert client._map_channel("tasks") == "task_events"
    assert client._map_channel("system") == "system_events"
    assert client._map_channel("logs:42") == "task_logs:42"
    assert client._map_channel("logs:abc-123") == "task_logs:abc-123"


@pytest.mark.asyncio
async def test_subscribe_increments_ref_count():
    """Subscribe should increment reference count."""
    client = CloudWebSocketClient()
    ws = AsyncMock()

    # Mock Valkey to prevent actual subscription
    with patch("cloud_client.get_valkey", return_value=None):
        await client._handle_subscribe(ws, {"channels": ["tasks"]})
        assert client._subscriptions.get("tasks") == 1

        await client._handle_subscribe(ws, {"channels": ["tasks"]})
        assert client._subscriptions.get("tasks") == 2


@pytest.mark.asyncio
async def test_unsubscribe_decrements_ref_count():
    """Unsubscribe should decrement reference count and remove at zero."""
    client = CloudWebSocketClient()

    # Set up initial subscription state
    client._subscriptions["tasks"] = 2
    # Create a real cancelled task
    async def noop():
        pass
    task = asyncio.create_task(noop())
    await task  # Let it complete
    client._subscription_tasks["tasks"] = task

    await client._handle_unsubscribe({"channels": ["tasks"]})
    assert client._subscriptions.get("tasks") == 1

    await client._handle_unsubscribe({"channels": ["tasks"]})
    assert "tasks" not in client._subscriptions


@pytest.mark.asyncio
async def test_push_event_format():
    """Push events should use correct message format."""
    client = CloudWebSocketClient()
    ws = AsyncMock()

    # Create a mock pubsub that yields one message then cancels
    class MockPubSub:
        def __init__(self):
            self._sent = False

        async def subscribe(self, channel):
            pass

        async def get_message(self, ignore_subscribe_messages=True, timeout=1.0):
            if not self._sent:
                self._sent = True
                return {
                    "type": "message",
                    "data": json.dumps({"event": "task_updated", "task": {"id": "1"}}),
                }
            raise asyncio.CancelledError()

        async def unsubscribe(self, channel):
            pass

        async def aclose(self):
            pass

    mock_valkey = MagicMock()
    mock_valkey.pubsub.return_value = MockPubSub()

    with patch("cloud_client.get_valkey", return_value=mock_valkey):
        await client._forward_channel(ws, "tasks", "task_events")

    ws.send.assert_called_once()
    sent = json.loads(ws.send.call_args[0][0])
    assert sent["type"] == "push_event"
    assert sent["channel"] == "tasks"
    assert "task_updated" in sent["data"]


@pytest.mark.asyncio
async def test_cleanup_subscriptions():
    """Cleanup should cancel all forwarding tasks."""
    client = CloudWebSocketClient()

    async def noop():
        pass

    task1 = asyncio.create_task(noop())
    task2 = asyncio.create_task(noop())
    await task1
    await task2

    client._subscription_tasks = {"tasks": task1, "logs:1": task2}
    client._subscriptions = {"tasks": 1, "logs:1": 1}

    await client._cleanup_subscriptions()

    assert len(client._subscription_tasks) == 0
    assert len(client._subscriptions) == 0


@pytest.mark.asyncio
async def test_message_dispatch_routes_correctly():
    """_handle_message should route new message types correctly."""
    client = CloudWebSocketClient()
    ws = AsyncMock()

    with patch.object(client, '_handle_proxy_request', new_callable=AsyncMock) as mock_proxy, \
         patch.object(client, '_handle_subscribe', new_callable=AsyncMock) as mock_sub, \
         patch.object(client, '_handle_unsubscribe', new_callable=AsyncMock) as mock_unsub:

        await client._handle_message(ws, {"type": "proxy_request", "id": "1"})
        mock_proxy.assert_called_once()

        await client._handle_message(ws, {"type": "subscribe", "channels": ["tasks"]})
        mock_sub.assert_called_once()

        await client._handle_message(ws, {"type": "unsubscribe", "channels": ["tasks"]})
        mock_unsub.assert_called_once()
