"""Cloud endpoint management.

Handles automatic registration and revocation of webhook endpoints
with errand-cloud when both cloud and Slack credentials are active.
"""
import logging
import time as _time

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models import PlatformCredential, Setting, WebhookTrigger
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
        async with httpx.AsyncClient(follow_redirects=True) as client:
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
        async with httpx.AsyncClient(follow_redirects=True) as client:
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
        async with httpx.AsyncClient(follow_redirects=True) as client:
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


async def register_webhook_trigger_endpoint(
    cloud_creds: dict,
    cloud_service_url: str,
    trigger_id: str,
    integration: str,
    webhook_secret: str,
    label: str,
) -> dict | None:
    """Register a webhook trigger endpoint with errand-cloud.

    Returns the endpoint data on success, None on failure.
    """
    access_token = cloud_creds.get("access_token", "")
    if not access_token:
        return None

    api_url = f"{cloud_service_url.rstrip('/')}/api/endpoints"

    try:
        async with httpx.AsyncClient(follow_redirects=True) as client:
            resp = await client.post(
                api_url,
                json={
                    "integration": integration,
                    "endpoint_type": "webhook",
                    "trigger_id": trigger_id,
                    "webhook_secret": webhook_secret,
                    "label": label,
                },
                headers={"Authorization": f"Bearer {access_token}"},
                timeout=30,
            )
            if not resp.is_success:
                logger.error("Cloud webhook trigger registration failed: %s", resp.text)
                return None
            return resp.json()
    except Exception:
        logger.exception("Cloud webhook trigger registration API call failed")
        return None


async def deregister_webhook_trigger_endpoint(
    cloud_creds: dict,
    cloud_service_url: str,
    trigger_id: str,
    integration: str,
) -> None:
    """Deregister a webhook trigger endpoint from errand-cloud."""
    access_token = cloud_creds.get("access_token", "")
    if not access_token:
        return

    api_url = f"{cloud_service_url.rstrip('/')}/api/endpoints?integration={integration}&trigger_id={trigger_id}"

    try:
        async with httpx.AsyncClient(follow_redirects=True) as client:
            resp = await client.delete(
                api_url,
                headers={"Authorization": f"Bearer {access_token}"},
                timeout=30,
            )
            resp.raise_for_status()
            logger.info("Deregistered cloud endpoint for trigger %s", trigger_id)
    except Exception:
        logger.exception("Cloud webhook trigger deregistration failed for trigger %s", trigger_id)


async def _resolve_cloud_context(session: AsyncSession) -> tuple[dict, str] | None:
    """Resolve (cloud_creds, cloud_service_url) when cloud is connected. Returns None otherwise."""
    result = await session.execute(
        select(PlatformCredential).where(PlatformCredential.platform_id == "cloud")
    )
    cloud_cred = result.scalar_one_or_none()
    if not cloud_cred or cloud_cred.status != "connected":
        return None

    cloud_creds = decrypt_credentials(cloud_cred.encrypted_data)

    from settings_registry import SETTINGS_REGISTRY
    result = await session.execute(
        select(Setting).where(Setting.key == "cloud_service_url")
    )
    url_setting = result.scalar_one_or_none()
    cloud_service_url = url_setting.value if url_setting and url_setting.value else SETTINGS_REGISTRY["cloud_service_url"]["default"]
    return cloud_creds, cloud_service_url


async def register_webhook_trigger_with_cloud(
    trigger: WebhookTrigger, session: AsyncSession
) -> None:
    """Register a webhook trigger with errand-cloud and persist the URL/token.

    Best-effort: on cloud disconnected, returns silently. On HTTP failure, logs
    the error, stores the detail in `cloud_endpoint_error` Setting, leaves the
    trigger's cloud columns unchanged, and does NOT raise.
    """
    ctx = await _resolve_cloud_context(session)
    if ctx is None:
        logger.debug("Cloud not connected, skipping trigger endpoint registration for %s", trigger.id)
        return
    cloud_creds, cloud_service_url = ctx

    if not trigger.webhook_secret:
        logger.debug("Trigger %s has no webhook_secret, skipping cloud registration", trigger.id)
        return

    try:
        secret_data = decrypt_credentials(trigger.webhook_secret)
        plaintext_secret = secret_data.get("secret", "")
    except Exception:
        logger.exception("Failed to decrypt webhook_secret for trigger %s", trigger.id)
        return

    if not plaintext_secret:
        logger.debug("Empty webhook_secret for trigger %s, skipping cloud registration", trigger.id)
        return

    access_token = cloud_creds.get("access_token", "")
    if not access_token:
        return

    api_url = f"{cloud_service_url.rstrip('/')}/api/endpoints"
    body = {
        "integration": trigger.source,
        "endpoint_type": "webhook",
        "trigger_id": str(trigger.id),
        "webhook_secret": plaintext_secret,
        "label": trigger.name,
    }

    try:
        async with httpx.AsyncClient(follow_redirects=True) as client:
            resp = await client.post(
                api_url,
                json=body,
                headers={"Authorization": f"Bearer {access_token}"},
                timeout=30,
            )
            if not resp.is_success:
                level = logging.WARNING if resp.status_code == 403 else logging.ERROR
                logger.log(
                    level,
                    "Cloud webhook trigger registration failed for %s: %s %s — body: %s",
                    trigger.id, resp.status_code, resp.reason_phrase, resp.text,
                )
                try:
                    error_detail = resp.json().get("detail", resp.text)
                except Exception:
                    error_detail = resp.text
                await _store_endpoint_error(session, error_detail)
                return
            data = resp.json()
    except Exception:
        logger.exception("Cloud webhook trigger registration API call failed for %s", trigger.id)
        await _store_endpoint_error(session, "Cloud endpoint registration failed (network or server error)")
        return

    url = data.get("url")
    token = data.get("token")
    if not url or not token:
        logger.error("Cloud webhook trigger registration response missing url/token for %s: %s", trigger.id, data)
        await _store_endpoint_error(session, "Cloud endpoint registration response missing url/token")
        return

    trigger.cloud_webhook_url = url
    trigger.cloud_endpoint_token = token
    await _clear_endpoint_error(session)
    await session.commit()
    logger.info("Registered cloud webhook endpoint for trigger %s (%s)", trigger.id, trigger.source)


async def revoke_webhook_trigger_in_cloud(
    trigger: WebhookTrigger, session: AsyncSession
) -> None:
    """Revoke a webhook trigger endpoint in errand-cloud.

    Prefers DELETE /api/endpoints/{token} when token is known; falls back to the
    bulk-delete query form otherwise. Best-effort — failures are logged and swallowed.
    """
    ctx = await _resolve_cloud_context(session)
    if ctx is None:
        return
    cloud_creds, cloud_service_url = ctx

    access_token = cloud_creds.get("access_token", "")
    if not access_token:
        return

    base = cloud_service_url.rstrip("/")
    if trigger.cloud_endpoint_token:
        api_url = f"{base}/api/endpoints/{trigger.cloud_endpoint_token}"
    else:
        api_url = f"{base}/api/endpoints?integration={trigger.source}&trigger_id={trigger.id}"

    try:
        async with httpx.AsyncClient(follow_redirects=True) as client:
            resp = await client.delete(
                api_url,
                headers={"Authorization": f"Bearer {access_token}"},
                timeout=30,
            )
            resp.raise_for_status()
            logger.info("Revoked cloud endpoint for trigger %s", trigger.id)
    except Exception:
        logger.exception("Cloud webhook trigger revocation failed for trigger %s", trigger.id)


async def revoke_cloud_endpoints_for_integration(
    cloud_creds: dict, cloud_service_url: str, integration: str
) -> None:
    """Bulk-revoke all cloud endpoints for a given integration (e.g. "jira", "github")."""
    access_token = cloud_creds.get("access_token", "")
    if not access_token:
        return

    api_url = f"{cloud_service_url.rstrip('/')}/api/endpoints?integration={integration}"
    try:
        async with httpx.AsyncClient(follow_redirects=True) as client:
            resp = await client.delete(
                api_url,
                headers={"Authorization": f"Bearer {access_token}"},
                timeout=30,
            )
            resp.raise_for_status()
            logger.info("Revoked cloud endpoints for integration %s", integration)
    except Exception:
        logger.exception("Cloud endpoint revocation failed for integration %s", integration)


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
        async with httpx.AsyncClient(follow_redirects=True) as client:
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
