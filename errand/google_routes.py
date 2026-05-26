"""HTTP routes for Google Workspace token operations.

Currently exposes the mid-task refresh endpoint (`POST /api/google/refresh-token`)
used by task-runner pods to recover from expired-token responses while a task
is in flight. See spec `google-workspace-integration`.
"""

import logging
import secrets

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from cloud_storage import force_refresh_token
from database import get_session
from models import Setting
from platforms.credentials import load_credentials

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/google", tags=["google"])

_bearer_scheme = HTTPBearer(auto_error=False)


async def _require_mcp_api_key(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer_scheme),
    session: AsyncSession = Depends(get_session),
) -> None:
    """Reject the request unless the Authorization header matches mcp_api_key."""
    if credentials is None or not credentials.credentials:
        raise HTTPException(status_code=401, detail="missing bearer token")

    result = await session.execute(
        select(Setting.value).where(Setting.key == "mcp_api_key")
    )
    stored_key = result.scalar_one_or_none()

    if not stored_key:
        raise HTTPException(status_code=401, detail="mcp_api_key not configured")

    if not secrets.compare_digest(credentials.credentials, stored_key):
        raise HTTPException(status_code=401, detail="invalid bearer token")


@router.post("/refresh-token", dependencies=[Depends(_require_mcp_api_key)])
async def refresh_google_token(
    request: Request,
    session: AsyncSession = Depends(get_session),
) -> dict:
    """Force-refresh the stored google_drive OAuth credential.

    Bypasses the 5-minute remaining-life buffer used at task-start. Intended
    for the task-runner's mid-task recovery path when it has observed an
    UNAUTHENTICATED response from a Google API call.
    """
    task_id = request.headers.get("X-Task-Id", "")

    creds = await load_credentials("google_drive", session)
    if not creds:
        logger.info(
            "refresh-token: provider=google_drive task_id=%s status=not_configured",
            task_id or "-",
        )
        raise HTTPException(status_code=404, detail="no Google credentials configured")

    refreshed = await force_refresh_token("google_drive", creds, session)
    if not refreshed:
        logger.warning(
            "refresh-token: provider=google_drive task_id=%s status=upstream_failed",
            task_id or "-",
        )
        raise HTTPException(status_code=502, detail="upstream refresh failed")

    logger.info(
        "refresh-token: provider=google_drive task_id=%s status=ok expires_at=%s",
        task_id or "-", refreshed.get("expires_at"),
    )

    return {
        "access_token": refreshed["access_token"],
        "expires_at": int(refreshed.get("expires_at", 0)),
    }
