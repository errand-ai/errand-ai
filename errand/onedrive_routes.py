"""HTTP routes for OneDrive token operations.

Exposes the mid-task / gateway refresh endpoint (`POST /api/onedrive/refresh-token`),
the OneDrive parallel of `google_routes.refresh_google_token`. It closes the
previously-known gap where OneDrive had no server-side refresh endpoint (its
token lived only in the MCP `Authorization` header, so a long-running consumer
like the shared-workspace gateway could not stay authenticated).

Authentication mirrors the Google endpoint: the request must carry either a
per-task OneDrive refresh bearer or the workspace-scoped gateway bearer (see
`workspace_refresh_auth`). The global `mcp_api_key` does NOT authenticate here.

Refresh flows through the same `cloud_storage.force_refresh_token` machinery as
Google, using the canonical provider name ``onedrive`` — a direct refresh when
local Microsoft client credentials are configured, otherwise via the errand-cloud
OAuth relay. Failures are returned as structured HTTP errors, never swallowed.
"""

import logging

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from cloud_storage import force_refresh_token
from database import get_session
from platforms.credentials import load_credentials
from workspace_refresh_auth import ONEDRIVE_TASK_BEARER_PREFIX, require_refresh_bearer

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/onedrive", tags=["onedrive"])

_PROVIDER = "onedrive"

_require_refresh_bearer = require_refresh_bearer(ONEDRIVE_TASK_BEARER_PREFIX)


@router.post("/refresh-token")
async def refresh_onedrive_token(
    request: Request,
    caller: str = Depends(_require_refresh_bearer),
    session: AsyncSession = Depends(get_session),
) -> dict:
    """Force-refresh the stored OneDrive OAuth credential.

    Bypasses the 5-minute remaining-life buffer used at task-start. Intended for
    the workspace gateway's token-refresher (and mid-task recovery) when it has
    evidence the token no longer works.
    """
    creds = await load_credentials(_PROVIDER, session)
    if not creds:
        logger.info(
            "refresh-token: provider=onedrive caller=%s status=not_configured",
            caller or "-",
        )
        raise HTTPException(status_code=404, detail="no OneDrive credentials configured")

    refreshed = await force_refresh_token(_PROVIDER, creds, session)
    if not refreshed:
        logger.warning(
            "refresh-token: provider=onedrive caller=%s status=upstream_failed",
            caller or "-",
        )
        raise HTTPException(status_code=502, detail="upstream refresh failed")

    logger.info(
        "refresh-token: provider=onedrive caller=%s status=ok expires_at=%s",
        caller or "-", refreshed.get("expires_at"),
    )

    return {
        "access_token": refreshed["access_token"],
        "expires_at": int(refreshed.get("expires_at", 0)),
    }
