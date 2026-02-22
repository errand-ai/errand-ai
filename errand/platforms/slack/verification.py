import hashlib
import hmac
import time

from fastapi import Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_session
from platforms.credentials import load_credentials


async def verify_slack_request(
    request: Request,
    session: AsyncSession = Depends(get_session),
) -> bytes:
    """FastAPI dependency that verifies Slack request signatures.

    Returns the raw request body on success so downstream handlers can parse it.
    """
    credentials = await load_credentials("slack", session)
    if not credentials:
        raise HTTPException(status_code=503, detail="Slack is not configured")

    signing_secret = credentials.get("signing_secret", "")

    signature = request.headers.get("X-Slack-Signature")
    timestamp = request.headers.get("X-Slack-Request-Timestamp")

    if not signature or not timestamp:
        raise HTTPException(status_code=403, detail="Missing Slack signature headers")

    try:
        ts = int(timestamp)
    except ValueError:
        raise HTTPException(status_code=403, detail="Invalid timestamp")

    if abs(time.time() - ts) > 300:
        raise HTTPException(status_code=403, detail="Request timestamp too old")

    body = await request.body()
    basestring = f"v0:{timestamp}:{body.decode()}"
    computed = "v0=" + hmac.new(
        signing_secret.encode(), basestring.encode(), hashlib.sha256
    ).hexdigest()

    if not hmac.compare_digest(computed, signature):
        raise HTTPException(status_code=403, detail="Invalid signature")

    return body


def handle_url_verification(payload: dict) -> dict | None:
    """Handle Slack Events API URL verification challenge.

    If the payload is a url_verification event, returns the challenge response.
    Otherwise returns None so the caller knows to process the event normally.
    """
    if payload.get("type") == "url_verification":
        return {"challenge": payload.get("challenge", "")}
    return None
