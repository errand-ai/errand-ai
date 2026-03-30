"""Jira platform credential API routes."""

import logging
from datetime import datetime, timezone

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_session
from models import PlatformCredential
from platforms.credentials import encrypt, decrypt

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/credentials/jira", tags=["jira-credentials"])

JIRA_PLATFORM_ID = "jira"


async def _require_admin(request: Request):
    from main import require_admin
    from fastapi.security import HTTPBearer
    security = HTTPBearer(auto_error=True)
    credentials = await security(request)
    return await require_admin(request, credentials)


class JiraCredentialSave(BaseModel):
    cloud_id: str
    api_token: str
    site_url: str
    service_account_email: str


@router.put("")
async def save_jira_credentials(
    body: JiraCredentialSave,
    session: AsyncSession = Depends(get_session),
    _user: dict = Depends(_require_admin),
):
    # Verify credentials against Jira API
    verify_url = f"https://api.atlassian.com/ex/jira/{body.cloud_id}/rest/api/3/myself"
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                verify_url,
                headers={"Authorization": f"Bearer {body.api_token}"},
                timeout=10,
            )
    except httpx.RequestError as e:
        raise HTTPException(status_code=400, detail=f"Credential verification failed: {e}")

    if resp.status_code != 200:
        raise HTTPException(
            status_code=400,
            detail=f"Credential verification failed: Jira returned {resp.status_code}",
        )

    jira_user = resp.json()
    display_name = jira_user.get("displayName", "")

    credential_data = {
        "cloud_id": body.cloud_id,
        "api_token": body.api_token,
        "site_url": body.site_url,
        "service_account_email": body.service_account_email,
    }
    encrypted = encrypt(credential_data)

    # Upsert
    await session.execute(
        delete(PlatformCredential).where(PlatformCredential.platform_id == JIRA_PLATFORM_ID)
    )
    now = datetime.now(timezone.utc)
    session.add(PlatformCredential(
        platform_id=JIRA_PLATFORM_ID,
        encrypted_data=encrypted,
        status="connected",
        last_verified_at=now,
    ))
    await session.commit()

    return {
        "platform_id": JIRA_PLATFORM_ID,
        "status": "connected",
        "display_name": display_name,
        "site_url": body.site_url,
    }


@router.get("")
async def get_jira_credential_status(
    session: AsyncSession = Depends(get_session),
    _user: dict = Depends(_require_admin),
):
    result = await session.execute(
        select(PlatformCredential).where(PlatformCredential.platform_id == JIRA_PLATFORM_ID)
    )
    cred = result.scalar_one_or_none()
    if not cred:
        return {
            "platform_id": JIRA_PLATFORM_ID,
            "status": "disconnected",
            "site_url": None,
            "last_verified_at": None,
        }

    try:
        cred_data = decrypt(cred.encrypted_data)
    except Exception:
        logger.warning("Failed to decrypt Jira credentials, reporting as disconnected")
        return {
            "platform_id": JIRA_PLATFORM_ID,
            "status": "error",
            "site_url": None,
            "last_verified_at": None,
        }
    return {
        "platform_id": JIRA_PLATFORM_ID,
        "status": cred.status,
        "site_url": cred_data.get("site_url"),
        "last_verified_at": cred.last_verified_at.isoformat() if cred.last_verified_at else None,
    }


@router.delete("", status_code=204)
async def delete_jira_credentials(
    session: AsyncSession = Depends(get_session),
    _user: dict = Depends(_require_admin),
):
    await session.execute(
        delete(PlatformCredential).where(PlatformCredential.platform_id == JIRA_PLATFORM_ID)
    )
    await session.commit()
