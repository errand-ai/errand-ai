"""Cloud endpoint management.

Handles automatic registration and revocation of webhook endpoints
with errand-cloud when both cloud and Slack credentials are active.
"""
import logging
import time as _time

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models import PlatformCredential, Setting
from platforms.credentials import decrypt as decrypt_credentials

logger = logging.getLogger(__name__)


async def register_cloud_endpoints(
    cloud_creds: dict,
    slack_creds: dict,
    cloud_service_url: str,
    session: AsyncSession,
) -> list[dict] | None:
    """Register webhook endpoints with errand-cloud.

    Calls POST /api/endpoints on errand-cloud with the Slack signing secret.
    Stores returned endpoint URLs in the cloud_endpoints setting.
    Returns the list of endpoints on success, None on failure.
    """
    access_token = cloud_creds.get("access_token", "")
    signing_secret = slack_creds.get("signing_secret", "")

    if not access_token or not signing_secret:
        logger.warning("Missing access_token or signing_secret for cloud endpoint registration")
        return None

    api_url = f"{cloud_service_url.rstrip('/')}/api/endpoints"

    try:
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                api_url,
                json={
                    "integration": "slack",
                    "label": "errand-instance",
                    "signing_secret": signing_secret,
                },
                headers={"Authorization": f"Bearer {access_token}"},
                timeout=30,
            )
            if not resp.is_success:
                logger.error(
                    "Cloud endpoint registration failed: %s %s — body: %s",
                    resp.status_code,
                    resp.reason_phrase,
                    resp.text,
                )
                # Extract detail from JSON response if possible
                try:
                    error_detail = resp.json().get("detail", resp.text)
                except Exception:
                    error_detail = resp.text
                await _store_endpoint_error(session, error_detail)
                return None
            data = resp.json()
    except Exception:
        logger.exception("Cloud endpoint registration API call failed")
        await _store_endpoint_error(session, "Cloud endpoint registration failed (network or server error)")
        return None

    # Store endpoint URLs in settings
    endpoints = data.get("endpoints", [])
    endpoint_list = [
        {
            "integration": data.get("integration", "slack"),
            "endpoint_type": ep.get("type", ""),
            "url": ep.get("url", ""),
            "token": ep.get("token", ""),
        }
        for ep in endpoints
    ]

    result = await session.execute(
        select(Setting).where(Setting.key == "cloud_endpoints")
    )
    existing = result.scalar_one_or_none()
    if existing:
        existing.value = endpoint_list
    else:
        session.add(Setting(key="cloud_endpoints", value=endpoint_list))

    # Clear any previous endpoint error on success
    await _clear_endpoint_error(session)
    await session.commit()

    logger.info("Registered %d cloud endpoints", len(endpoint_list))
    return endpoint_list


async def revoke_cloud_endpoints(cloud_creds: dict, cloud_service_url: str) -> None:
    """Revoke all Slack endpoints on errand-cloud.

    Calls DELETE /api/endpoints?integration=slack.
    """
    access_token = cloud_creds.get("access_token", "")
    if not access_token:
        return

    api_url = f"{cloud_service_url.rstrip('/')}/api/endpoints?integration=slack"

    try:
        async with httpx.AsyncClient() as client:
            resp = await client.delete(
                api_url,
                headers={"Authorization": f"Bearer {access_token}"},
                timeout=30,
            )
            resp.raise_for_status()
            logger.info("Revoked cloud endpoints for slack")
    except Exception:
        logger.exception("Cloud endpoint revocation API call failed")


async def check_existing_endpoints(cloud_creds: dict, cloud_service_url: str) -> list[dict]:
    """Check for existing Slack endpoints on errand-cloud.

    Calls GET /api/endpoints?integration=slack.
    Returns the list of existing endpoints.
    """
    access_token = cloud_creds.get("access_token", "")
    if not access_token:
        return []

    api_url = f"{cloud_service_url.rstrip('/')}/api/endpoints?integration=slack"

    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                api_url,
                headers={"Authorization": f"Bearer {access_token}"},
                timeout=30,
            )
            resp.raise_for_status()
            return resp.json()
    except Exception:
        logger.exception("Cloud endpoint check API call failed")
        return []


async def try_register_endpoints(session: AsyncSession) -> None:
    """Register cloud endpoints if both cloud and Slack credentials are active.

    Checks for existing endpoints before creating new ones (idempotent).
    """
    # Load cloud credentials
    result = await session.execute(
        select(PlatformCredential).where(PlatformCredential.platform_id == "cloud")
    )
    cloud_cred = result.scalar_one_or_none()
    if not cloud_cred or cloud_cred.status != "connected":
        return

    cloud_creds = decrypt_credentials(cloud_cred.encrypted_data)

    # Load Slack credentials
    result = await session.execute(
        select(PlatformCredential).where(PlatformCredential.platform_id == "slack")
    )
    slack_cred = result.scalar_one_or_none()
    if not slack_cred or slack_cred.status != "connected":
        return

    slack_creds = decrypt_credentials(slack_cred.encrypted_data)

    # Get cloud service URL
    from settings_registry import SETTINGS_REGISTRY
    result = await session.execute(
        select(Setting).where(Setting.key == "cloud_service_url")
    )
    url_setting = result.scalar_one_or_none()
    cloud_service_url = url_setting.value if url_setting and url_setting.value else SETTINGS_REGISTRY["cloud_service_url"]["default"]

    # Check for existing endpoints
    existing = await check_existing_endpoints(cloud_creds, cloud_service_url)
    if existing:
        # Persist existing endpoints to local setting so the UI can display them
        endpoint_list = [
            {
                "integration": ep.get("integration", "slack"),
                "endpoint_type": ep.get("type", ep.get("endpoint_type", "")),
                "url": ep.get("url", ""),
                "token": ep.get("token", ""),
            }
            for ep in existing
        ]
        result = await session.execute(
            select(Setting).where(Setting.key == "cloud_endpoints")
        )
        ep_setting = result.scalar_one_or_none()
        if ep_setting:
            ep_setting.value = endpoint_list
        else:
            session.add(Setting(key="cloud_endpoints", value=endpoint_list))
        await session.commit()
        logger.info("Cloud endpoints already exist for slack, persisted %d to local setting", len(endpoint_list))
        return

    await register_cloud_endpoints(cloud_creds, slack_creds, cloud_service_url, session)


async def _store_endpoint_error(session: AsyncSession, detail: str) -> None:
    """Store an endpoint registration error in the cloud_endpoint_error Setting."""
    error_data = {"detail": detail, "timestamp": _time.time()}
    result = await session.execute(
        select(Setting).where(Setting.key == "cloud_endpoint_error")
    )
    existing = result.scalar_one_or_none()
    if existing:
        existing.value = error_data
    else:
        session.add(Setting(key="cloud_endpoint_error", value=error_data))
    await session.commit()


async def _clear_endpoint_error(session: AsyncSession) -> None:
    """Delete the cloud_endpoint_error Setting if it exists."""
    result = await session.execute(
        select(Setting).where(Setting.key == "cloud_endpoint_error")
    )
    existing = result.scalar_one_or_none()
    if existing:
        await session.delete(existing)


async def fetch_subscription_status(
    cloud_creds: dict, cloud_service_url: str
) -> dict | None:
    """Fetch subscription status from the cloud service.

    Calls GET /api/subscription with Bearer auth.
    Returns {active: bool, expires_at: str | None} or None on failure.
    """
    access_token = cloud_creds.get("access_token", "")
    if not access_token:
        return None

    api_url = f"{cloud_service_url.rstrip('/')}/api/subscription"

    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                api_url,
                headers={"Authorization": f"Bearer {access_token}"},
                timeout=10,
            )
            if not resp.is_success:
                logger.debug("Cloud subscription check returned %s", resp.status_code)
                return None
            data = resp.json()
            if not isinstance(data, dict):
                return None
            active = data.get("active")
            expires_at = data.get("expires_at")
            if not isinstance(active, bool):
                return None
            if expires_at is not None and not isinstance(expires_at, str):
                return None
            return {"active": active, "expires_at": expires_at}
    except Exception:
        logger.debug("Cloud subscription check failed", exc_info=True)
        return None
