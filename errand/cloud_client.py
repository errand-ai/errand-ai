"""Cloud WebSocket client for errand-cloud relay.

Maintains a persistent WebSocket connection to errand-cloud, receives
relayed webhook payloads, and dispatches them to the appropriate handlers.
"""
import asyncio
import json
import logging
import random
import time

import websockets

from database import async_session
from events import publish_event
from models import PlatformCredential, Setting
from platforms.credentials import decrypt as decrypt_credentials, encrypt as encrypt_credentials
from sqlalchemy import select

logger = logging.getLogger(__name__)

# Module-level task reference for the WebSocket client
_client_task: asyncio.Task | None = None
_refresh_task: asyncio.Task | None = None


class CloudWebSocketClient:
    """Async WebSocket client implementing the errand-client-protocol."""

    # Close codes that should NOT auto-reconnect
    NO_RECONNECT_CODES = {4001, 4003}
    AUTH_EXPIRED_CODE = 4002

    def __init__(self):
        self._processed_ids: set[str] = set()
        self._running = False
        self._backoff_attempt = 0

    async def run(self) -> None:
        """Main run loop with reconnection logic."""
        self._running = True
        while self._running:
            try:
                await self._connect_and_receive()
            except asyncio.CancelledError:
                logger.info("Cloud WebSocket client cancelled")
                break
            except Exception:
                logger.exception("Cloud WebSocket connection error")

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
                self._backoff_attempt = 0
                self._processed_ids.clear()
                logger.info("Connected to cloud WebSocket: %s", cloud_url)
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
            from cloud_auth import refresh_token, get_keycloak_urls

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

                # Get cloud config for token URL
                result = await session.execute(
                    select(Setting).where(Setting.key == "cloud_service_url")
                )
                url_setting = result.scalar_one_or_none()
                cloud_url = url_setting.value if url_setting and url_setting.value else "https://service.errand.cloud"

                result = await session.execute(
                    select(Setting).where(Setting.key == "cloud_keycloak_realm_url")
                )
                realm_setting = result.scalar_one_or_none()
                realm_url = realm_setting.value if realm_setting and realm_setting.value else None

                result = await session.execute(
                    select(Setting).where(Setting.key == "cloud_keycloak_client_id")
                )
                client_setting = result.scalar_one_or_none()
                client_id = client_setting.value if client_setting and client_setting.value else "errand-desktop"

                urls = get_keycloak_urls(cloud_url, realm_url, client_id)

                tokens = await refresh_token(
                    token_url=urls["token_url"],
                    client_id=urls["client_id"],
                    refresh_token_value=refresh_token_value,
                )

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
    global _client_task, _refresh_task

    if _client_task and not _client_task.done():
        _client_task.cancel()
        try:
            await _client_task
        except asyncio.CancelledError:
            pass
    _client_task = None

    if _refresh_task and not _refresh_task.done():
        _refresh_task.cancel()
        try:
            await _refresh_task
        except asyncio.CancelledError:
            pass
    _refresh_task = None
    logger.info("Cloud WebSocket client stopped")
