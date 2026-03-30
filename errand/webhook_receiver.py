"""Webhook receiver endpoint.

Receives webhooks from external sources (direct and cloud-relayed),
verifies HMAC signatures, and dispatches to source handlers.
"""

import asyncio
import hashlib
import hmac
import logging
import time
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_session
from models import WebhookTrigger
from platforms.credentials import decrypt

logger = logging.getLogger(__name__)

router = APIRouter(tags=["webhooks"])

# Source-specific header configuration
SOURCE_HEADERS = {
    "jira": {
        "signature": "X-Hub-Signature",
        "event_id": "X-Atlassian-Webhook-Identifier",
    },
    "github": {
        "signature": "X-Hub-Signature-256",
        "event_id": "X-GitHub-Delivery",
    },
}

# TTL cache for deduplication: event_id -> timestamp
_dedup_cache: dict[str, float] = {}
DEDUP_TTL = 300  # 5 minutes


def _cleanup_dedup_cache() -> None:
    """Remove expired entries from the dedup cache."""
    now = time.monotonic()
    expired = [k for k, v in _dedup_cache.items() if now - v > DEDUP_TTL]
    for k in expired:
        del _dedup_cache[k]


def _is_duplicate(event_id: str) -> bool:
    """Check if an event has been seen recently."""
    _cleanup_dedup_cache()
    if event_id in _dedup_cache:
        return True
    _dedup_cache[event_id] = time.monotonic()
    return False


def _verify_hmac(secret: str, body: bytes, signature: str) -> bool:
    """Verify HMAC-SHA256 signature. Handles sha256= prefix."""
    sig = signature.removeprefix("sha256=")
    expected = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, sig)


async def find_matching_trigger(
    source: str, body: bytes, signature: str, session: AsyncSession,
) -> Optional[WebhookTrigger]:
    """Find the trigger whose secret matches the signature."""
    result = await session.execute(
        select(WebhookTrigger).where(
            WebhookTrigger.source == source,
            WebhookTrigger.enabled == True,
        )
    )
    triggers = result.scalars().all()

    for trigger in triggers:
        if not trigger.webhook_secret:
            continue
        try:
            cred_data = decrypt(trigger.webhook_secret)
            secret = cred_data.get("secret", "")
        except Exception:
            logger.warning("Failed to decrypt secret for trigger %s", trigger.id)
            continue
        if _verify_hmac(secret, body, signature):
            return trigger
    return None


async def _dispatch_webhook(trigger: WebhookTrigger, body: bytes, headers: dict) -> None:
    """Dispatch webhook to the appropriate source handler."""
    try:
        if trigger.source == "jira":
            from platforms.jira.handler import handle_jira_webhook
            await handle_jira_webhook(trigger, body, headers)
        else:
            logger.warning("No handler for webhook source: %s", trigger.source)
    except Exception:
        logger.exception("Error processing webhook for trigger %s (source=%s)", trigger.id, trigger.source)


@router.post("/webhooks/{source}")
async def receive_webhook(
    source: str,
    request: Request,
    session: AsyncSession = Depends(get_session),
):
    """Receive and route an incoming webhook."""
    headers_config = SOURCE_HEADERS.get(source)
    if not headers_config:
        headers_config = {"signature": "X-Hub-Signature", "event_id": None}

    # Extract signature
    signature_header = headers_config["signature"]
    signature = request.headers.get(signature_header)
    if not signature:
        raise HTTPException(status_code=401, detail="No matching trigger")

    # Read raw body
    body = await request.body()
    if not body:
        raise HTTPException(status_code=400, detail="Empty request body")

    # Deduplication
    event_id_header = headers_config.get("event_id")
    event_id = request.headers.get(event_id_header) if event_id_header else None
    if event_id and _is_duplicate(event_id):
        return {"status": "duplicate"}

    # HMAC routing
    trigger = await find_matching_trigger(source, body, signature, session)
    if not trigger:
        raise HTTPException(status_code=401, detail="No matching trigger")

    logger.info(
        "Webhook matched: source=%s trigger=%s event_id=%s",
        source, trigger.id, event_id,
    )

    # Dispatch asynchronously
    raw_headers = dict(request.headers)
    asyncio.create_task(_dispatch_webhook(trigger, body, raw_headers))

    return {"status": "accepted"}
