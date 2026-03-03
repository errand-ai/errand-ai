"""Cloud WebSocket client for errand-cloud relay.

Maintains a persistent WebSocket connection to errand-cloud, receives
relayed webhook payloads, and dispatches them to the appropriate handlers.
"""
import asyncio
import json
import logging
import os
import random
import time

import httpx
import websockets

from database import async_session
from events import get_valkey, publish_event
from models import PlatformCredential, Setting
from platforms.credentials import decrypt as decrypt_credentials, encrypt as encrypt_credentials
from sqlalchemy import select

logger = logging.getLogger(__name__)

# Module-level task reference for the WebSocket client
_client_task: asyncio.Task | None = None
_refresh_task: asyncio.Task | None = None
_ws_connected: bool = False


def is_connected() -> bool:
    """Return whether the cloud WebSocket is currently connected."""
    return _ws_connected


class CloudWebSocketClient:
    """Async WebSocket client implementing the errand-client-protocol."""

    # Close codes that should NOT auto-reconnect
    NO_RECONNECT_CODES = {4001, 4003}
    AUTH_EXPIRED_CODE = 4002

    # Channel name mapping: cloud channel → Valkey pub/sub channel
    CHANNEL_MAP = {
        "tasks": "task_events",
        "system": "system_events",
    }

    PROTOCOL_VERSION = 2

    def __init__(self):
        self._processed_ids: set[str] = set()
        self._running = False
        self._backoff_attempt = 0
        # Reference-counted subscriptions: channel_name → ref_count
        self._subscriptions: dict[str, int] = {}
        # Active subscription forwarding tasks
        self._subscription_tasks: dict[str, asyncio.Task] = {}
        # WebSocket reference for sending push_events
        self._ws = None
        # Server port for proxy requests
        self._server_port = int(os.environ.get("PORT", "8000"))

    async def run(self) -> None:
        """Main run loop with reconnection logic."""
        global _ws_connected
        self._running = True
        while self._running:
            try:
                await self._connect_and_receive()
            except asyncio.CancelledError:
                logger.info("Cloud WebSocket client cancelled")
                _ws_connected = False
                break
            except Exception:
                logger.exception("Cloud WebSocket connection error")
            _ws_connected = False

            if not self._running:
                break

            # Exponential backoff
            delay = self._backoff_delay()
            self._backoff_attempt += 1
            logger.info("Cloud WebSocket reconnecting in %.1fs (attempt %d)", delay, self._backoff_attempt)
            await publish_event("cloud_status", {"status": "disconnected"})
            try:
                await asyncio.sleep(delay)
            except asyncio.CancelledError:
                break

    async def _connect_and_receive(self) -> None:
        """Connect to cloud WebSocket and process messages."""
        cred_data = await self._load_credentials()
        if not cred_data:
            logger.warning("No cloud credentials found, stopping client")
            self._running = False
            return

        access_token = cred_data.get("access_token", "")
        cloud_url = await self._get_cloud_ws_url()

        headers = {"Authorization": f"Bearer {access_token}"}

        try:
            async with websockets.connect(cloud_url, additional_headers=headers) as ws:
                global _ws_connected
                self._backoff_attempt = 0
                self._processed_ids.clear()
                self._subscriptions.clear()
                self._ws = ws
                _ws_connected = True
                logger.info("Connected to cloud WebSocket: %s", cloud_url)

                # Send register message and wait for registered acknowledgement
                await self._send_register(ws)
                if not await self._wait_for_registered(ws):
                    logger.warning("Did not receive 'registered' acknowledgement")
                    return

                await publish_event("cloud_status", {"status": "connected"})

                async for raw_message in ws:
                    if not self._running:
                        break
                    try:
                        message = json.loads(raw_message)
                        await self._handle_message(ws, message)
                    except json.JSONDecodeError:
                        logger.warning("Cloud WebSocket received non-JSON message")
                    except Exception:
                        logger.exception("Error handling cloud WebSocket message")

                # Clean up subscriptions on disconnect
                await self._cleanup_subscriptions()

        except websockets.exceptions.ConnectionClosedError as e:
            await self._handle_close(e.code, e.reason)
        except websockets.exceptions.InvalidStatusCode as e:
            if e.status_code == 401:
                logger.warning("Cloud WebSocket rejected with 401, attempting token refresh")
                refreshed = await self._try_refresh_token()
                if not refreshed:
                    await self._set_credential_status("error")
                    await publish_event("cloud_status", {"status": "error", "detail": "Authentication failed"})
                    self._running = False

    async def _handle_message(self, ws, message: dict) -> None:
        """Dispatch a received message by type."""
        msg_type = message.get("type")

        if msg_type == "ping":
            ts = message.get("ts")
            await ws.send(json.dumps({"type": "pong", "ts": ts}))

        elif msg_type == "webhook":
            msg_id = message.get("id", "")

            # Deduplication
            if msg_id in self._processed_ids:
                await ws.send(json.dumps({"type": "ack", "id": msg_id}))
                return

            # Dispatch to handler
            try:
                from cloud_dispatch import dispatch_cloud_webhook
                await dispatch_cloud_webhook(message)
            except Exception:
                logger.exception("Cloud webhook dispatch failed for message %s", msg_id)

            # ACK regardless of dispatch success (prevent redelivery of unprocessable messages)
            if msg_id:
                self._processed_ids.add(msg_id)
            await ws.send(json.dumps({"type": "ack", "id": msg_id}))

        elif msg_type == "proxy_request":
            await self._handle_proxy_request(ws, message)

        elif msg_type == "subscribe":
            await self._handle_subscribe(ws, message)

        elif msg_type == "unsubscribe":
            await self._handle_unsubscribe(message)

    # --- Registration ---

    async def _send_register(self, ws) -> None:
        """Send register message with version and capabilities."""
        from capabilities import get_capabilities, get_server_version

        version = get_server_version()
        capabilities = await get_capabilities()

        register_msg = {
            "type": "register",
            "server_version": version,
            "protocol_version": self.PROTOCOL_VERSION,
            "capabilities": capabilities,
        }
        await ws.send(json.dumps(register_msg))
        logger.info("Sent register message: version=%s, capabilities=%s", version, capabilities)

    async def _wait_for_registered(self, ws, timeout: float = 10.0) -> bool:
        """Wait for 'registered' acknowledgement from cloud."""
        try:
            raw = await asyncio.wait_for(ws.recv(), timeout=timeout)
            message = json.loads(raw)
            if message.get("type") == "registered":
                logger.info("Received 'registered' acknowledgement from cloud")
                return True
            # Got a different message — handle it and keep waiting
            await self._handle_message(ws, message)
            return True  # Proceed even if we didn't get 'registered' explicitly
        except asyncio.TimeoutError:
            logger.warning("Timed out waiting for 'registered' acknowledgement")
            return True  # Proceed anyway — cloud may not support v2 yet
        except Exception:
            logger.exception("Error waiting for 'registered' acknowledgement")
            return False

    # --- Proxy request handling ---

    async def _handle_proxy_request(self, ws, message: dict) -> None:
        """Handle proxy_request: forward HTTP request to local API."""
        request_id = message.get("id", "")
        method = message.get("method", "GET").upper()
        path = message.get("path", "/")
        headers = message.get("headers", {})
        body = message.get("body")
        cloud_jwt = message.get("jwt")

        # Build request headers — inject X-Cloud-JWT and proxy secret for cloud-trusted auth
        from cloud_auth_jwt import PROXY_SECRET, PROXY_SECRET_HEADER

        req_headers = dict(headers)
        req_headers[PROXY_SECRET_HEADER] = PROXY_SECRET
        if cloud_jwt:
            req_headers["X-Cloud-JWT"] = cloud_jwt

        url = f"http://localhost:{self._server_port}{path}"

        try:
            async with httpx.AsyncClient() as client:
                response = await client.request(
                    method=method,
                    url=url,
                    headers=req_headers,
                    content=body.encode() if body else None,
                    timeout=30.0,
                )

            # Package response
            resp_headers = dict(response.headers)
            proxy_response = {
                "type": "proxy_response",
                "id": request_id,
                "status": response.status_code,
                "headers": resp_headers,
                "body": response.text,
            }
            await ws.send(json.dumps(proxy_response))

        except Exception:
            logger.exception("Proxy request failed: %s %s", method, path)
            error_response = {
                "type": "proxy_response",
                "id": request_id,
                "status": 502,
                "headers": {},
                "body": json.dumps({"detail": "Proxy request failed"}),
            }
            await ws.send(json.dumps(error_response))

    # --- Subscribe/unsubscribe handling ---

    def _map_channel(self, channel: str) -> str:
        """Map cloud channel name to Valkey pub/sub channel name."""
        if channel in self.CHANNEL_MAP:
            return self.CHANNEL_MAP[channel]
        # Handle logs:{task_id} → task_logs:{task_id}
        if channel.startswith("logs:"):
            task_id = channel[5:]
            return f"task_logs:{task_id}"
        return channel

    async def _handle_subscribe(self, ws, message: dict) -> None:
        """Handle subscribe message — start forwarding events for channels."""
        channels = message.get("channels", [])
        for channel in channels:
            self._subscriptions[channel] = self._subscriptions.get(channel, 0) + 1
            if self._subscriptions[channel] == 1:
                # First subscription — start forwarding
                valkey_channel = self._map_channel(channel)
                task = asyncio.create_task(self._forward_channel(ws, channel, valkey_channel))
                self._subscription_tasks[channel] = task
                logger.debug("Subscribed to channel: %s → %s", channel, valkey_channel)

    async def _handle_unsubscribe(self, message: dict) -> None:
        """Handle unsubscribe message — stop forwarding events for channels."""
        channels = message.get("channels", [])
        for channel in channels:
            if channel in self._subscriptions:
                self._subscriptions[channel] -= 1
                if self._subscriptions[channel] <= 0:
                    del self._subscriptions[channel]
                    # Cancel forwarding task
                    task = self._subscription_tasks.pop(channel, None)
                    if task:
                        task.cancel()
                        try:
                            await task
                        except asyncio.CancelledError:
                            pass
                    logger.debug("Unsubscribed from channel: %s", channel)

    async def _forward_channel(self, ws, cloud_channel: str, valkey_channel: str) -> None:
        """Forward events from a Valkey pub/sub channel as push_event messages."""
        valkey = get_valkey()
        if valkey is None:
            logger.warning("Cannot subscribe to %s — Valkey not connected", valkey_channel)
            return

        pubsub = valkey.pubsub()
        await pubsub.subscribe(valkey_channel)
        try:
            while True:
                msg = await pubsub.get_message(ignore_subscribe_messages=True, timeout=1.0)
                if msg and msg["type"] == "message":
                    push_event = {
                        "type": "push_event",
                        "channel": cloud_channel,
                        "data": msg["data"],
                    }
                    await ws.send(json.dumps(push_event))
        except asyncio.CancelledError:
            pass
        except Exception:
            logger.exception("Error forwarding channel %s", valkey_channel)
        finally:
            await pubsub.unsubscribe(valkey_channel)
            await pubsub.aclose()

    async def _cleanup_subscriptions(self) -> None:
        """Cancel all active subscription forwarding tasks."""
        for task in self._subscription_tasks.values():
            task.cancel()
        for task in self._subscription_tasks.values():
            try:
                await task
            except asyncio.CancelledError:
                pass
        self._subscription_tasks.clear()
        self._subscriptions.clear()

    async def _handle_close(self, code: int | None, reason: str | None) -> None:
        """Handle WebSocket close codes per errand-client-protocol."""
        logger.info("Cloud WebSocket closed: code=%s reason=%s", code, reason)

        if code == 4001:
            # Superseded — another instance took over
            await publish_event("cloud_status", {"status": "disconnected", "detail": "Connection taken over by another instance"})
            self._running = False

        elif code == self.AUTH_EXPIRED_CODE:
            # Auth expired — try refresh
            refreshed = await self._try_refresh_token()
            if not refreshed:
                await self._set_credential_status("error")
                await publish_event("cloud_status", {"status": "error", "detail": "Authentication expired"})
                self._running = False

        elif code == 4003:
            # Tenant disabled
            await self._set_credential_status("error")
            await publish_event("cloud_status", {"status": "error", "detail": "Account suspended"})
            self._running = False

    def _backoff_delay(self) -> float:
        """Calculate exponential backoff delay with jitter."""
        if self._backoff_attempt == 0:
            return random.uniform(0, 0.5)
        base = min(2 ** self._backoff_attempt, 30)
        return base * (0.5 + random.random() * 0.5)

    async def _load_credentials(self) -> dict | None:
        """Load cloud credentials from the database."""
        async with async_session() as session:
            result = await session.execute(
                select(PlatformCredential).where(PlatformCredential.platform_id == "cloud")
            )
            cred = result.scalar_one_or_none()
            if cred is None or cred.status != "connected":
                return None
            try:
                return decrypt_credentials(cred.encrypted_data)
            except Exception:
                return None

    async def _get_cloud_ws_url(self) -> str:
        """Get the WebSocket URL for the cloud service."""
        async with async_session() as session:
            result = await session.execute(
                select(Setting).where(Setting.key == "cloud_service_url")
            )
            setting = result.scalar_one_or_none()
            cloud_url = setting.value if setting and setting.value else "https://service.errand.cloud"

        # Convert https:// to wss://
        ws_url = cloud_url.replace("https://", "wss://").replace("http://", "ws://")
        return f"{ws_url.rstrip('/')}/ws"

    async def _try_refresh_token(self) -> bool:
        """Attempt to refresh the cloud access token. Returns True on success."""
        try:
            from cloud_auth import refresh_token

            async with async_session() as session:
                result = await session.execute(
                    select(PlatformCredential).where(PlatformCredential.platform_id == "cloud")
                )
                cred = result.scalar_one_or_none()
                if not cred:
                    return False

                cred_data = decrypt_credentials(cred.encrypted_data)
                refresh_token_value = cred_data.get("refresh_token", "")
                if not refresh_token_value:
                    return False

                # Get cloud service URL
                result = await session.execute(
                    select(Setting).where(Setting.key == "cloud_service_url")
                )
                url_setting = result.scalar_one_or_none()
                cloud_url = url_setting.value if url_setting and url_setting.value else "https://service.errand.cloud"

                tokens = await refresh_token(cloud_url, refresh_token_value)

                # Update stored credentials
                import time as _time
                cred_data["access_token"] = tokens["access_token"]
                if "refresh_token" in tokens:
                    cred_data["refresh_token"] = tokens["refresh_token"]
                cred_data["token_expiry"] = _time.time() + tokens.get("expires_in", 300)

                cred.encrypted_data = encrypt_credentials(cred_data)
                await session.commit()

                logger.info("Cloud access token refreshed successfully")
                return True

        except Exception:
            logger.exception("Cloud token refresh failed")
            return False

    async def _set_credential_status(self, status: str) -> None:
        """Update the cloud PlatformCredential status."""
        try:
            async with async_session() as session:
                result = await session.execute(
                    select(PlatformCredential).where(PlatformCredential.platform_id == "cloud")
                )
                cred = result.scalar_one_or_none()
                if cred:
                    cred.status = status
                    await session.commit()
        except Exception:
            logger.exception("Failed to update cloud credential status to %s", status)

    async def stop(self) -> None:
        """Signal the client to stop."""
        self._running = False


async def _run_token_refresh_loop() -> None:
    """Background task that periodically refreshes the cloud access token."""
    while True:
        try:
            await asyncio.sleep(30)  # Check every 30 seconds

            async with async_session() as session:
                result = await session.execute(
                    select(PlatformCredential).where(PlatformCredential.platform_id == "cloud")
                )
                cred = result.scalar_one_or_none()
                if not cred or cred.status != "connected":
                    continue

                cred_data = decrypt_credentials(cred.encrypted_data)
                token_expiry = cred_data.get("token_expiry", 0)

                # Refresh when within 60 seconds of expiry
                if time.time() >= token_expiry - 60:
                    client = CloudWebSocketClient()
                    refreshed = await client._try_refresh_token()
                    if not refreshed:
                        logger.warning("Token refresh failed, WebSocket will continue until server closes")
                        await publish_event("cloud_status", {"status": "error", "detail": "Token refresh failed"})

        except asyncio.CancelledError:
            break
        except Exception:
            logger.exception("Error in token refresh loop")


async def start_cloud_client() -> None:
    """Start the cloud WebSocket client and token refresh tasks."""
    global _client_task, _refresh_task

    # Stop existing tasks if running
    await stop_cloud_client()

    client = CloudWebSocketClient()
    _client_task = asyncio.create_task(client.run())
    _refresh_task = asyncio.create_task(_run_token_refresh_loop())
    logger.info("Cloud WebSocket client started")


async def stop_cloud_client() -> None:
    """Stop the cloud WebSocket client and token refresh tasks."""
    global _client_task, _refresh_task, _ws_connected

    if _client_task and not _client_task.done():
        _client_task.cancel()
        try:
            await _client_task
        except asyncio.CancelledError:
            pass  # Expected after cancel(); ensures task is fully awaited before cleanup
    _client_task = None

    if _refresh_task and not _refresh_task.done():
        _refresh_task.cancel()
        try:
            await _refresh_task
        except asyncio.CancelledError:
            pass  # Expected after cancel(); ensures task is fully awaited before cleanup
    _refresh_task = None
    _ws_connected = False
    logger.info("Cloud WebSocket client stopped")
