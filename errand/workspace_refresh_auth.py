"""Workspace-scoped bearer credential for the shared-workspace gateway.

The long-running workspace gateway's token-refresher sidecar calls the cloud
token-refresh endpoints (`/api/google/refresh-token`, `/api/onedrive/refresh-token`)
to keep rclone authenticated. It authenticates with a *workspace-scoped* opaque
bearer — deliberately NOT the deployment's `mcp_api_key` (which is readable by
every task via `/workspace/mcp.json`) and NOT a per-task bearer (the gateway is
not a task).

The bearer follows the same opaque-bearer-as-Valkey-key pattern as the per-task
Google refresh bearer: a random token is the lookup key, stored server-side under
`workspace_refresh_bearer:<bearer>`. It is usable ONLY on the token-refresh
endpoints (the refresh-endpoint dependency is the only code that consults the
`workspace_refresh_bearer:` prefix); presenting it to any other endpoint fails,
because every other endpoint authenticates via the admin session/JWT or the MCP
key.

Lifetime: the bearer is issued while the workspace is enabled and renewed on each
successful refresh call (an active gateway refreshes ~every 50 min, well inside
the TTL), so it outlives the gateway as long as the gateway keeps using it.
Disabling the workspace invalidates it (`invalidate_all_workspace_bearers`).

Issuance and invalidation *call sites* live with the workspace-enablement surface
(Helm/settings, later change sections); this module provides the primitives.
"""

import logging
import os
import secrets

from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from events import get_valkey

logger = logging.getLogger(__name__)

# Valkey key prefix under which each issued workspace bearer is stored.
WORKSPACE_BEARER_KEY_PREFIX = "workspace_refresh_bearer:"

# Task-scoped bearer key prefixes, per provider, used by the refresh endpoints.
GOOGLE_TASK_BEARER_PREFIX = "google_refresh_token:"
ONEDRIVE_TASK_BEARER_PREFIX = "onedrive_refresh_token:"

# TTL for a workspace bearer. Long-lived and renewed on each use so an active
# gateway never loses it; if the gateway stops using it (workspace torn down),
# it eventually expires on its own even without an explicit invalidation.
WORKSPACE_BEARER_TTL_SECONDS = int(
    os.environ.get("WORKSPACE_REFRESH_BEARER_TTL_SECONDS", str(24 * 60 * 60))
)


async def issue_workspace_bearer(valkey, *, ttl: int = WORKSPACE_BEARER_TTL_SECONDS) -> str:
    """Mint a new workspace bearer and store it in Valkey. Returns the bearer.

    The value stored under the key is irrelevant to authorization (presence is
    what authorizes); we store a fixed marker for readability.
    """
    bearer = secrets.token_hex(32)
    await valkey.set(f"{WORKSPACE_BEARER_KEY_PREFIX}{bearer}", "workspace", ex=ttl)
    return bearer


async def register_workspace_bearer(
    valkey, bearer: str, *, ttl: int = WORKSPACE_BEARER_TTL_SECONDS
) -> None:
    """Register an operator-supplied bearer value as a live workspace bearer.

    Unlike `issue_workspace_bearer` (which mints a random value), this activates
    a caller-supplied value — used at server startup to register the bearer that
    Helm/compose also injects into the gateway refresher, so the two sides share
    one credential without a separate issuance round-trip.
    """
    await valkey.set(f"{WORKSPACE_BEARER_KEY_PREFIX}{bearer}", "workspace", ex=ttl)


async def renew_workspace_bearer(
    valkey, bearer: str, *, ttl: int = WORKSPACE_BEARER_TTL_SECONDS
) -> bool:
    """Extend a workspace bearer's TTL. Returns True if the bearer existed."""
    key = f"{WORKSPACE_BEARER_KEY_PREFIX}{bearer}"
    try:
        return bool(await valkey.expire(key, ttl))
    except Exception:
        return False


async def invalidate_workspace_bearer(valkey, bearer: str) -> None:
    """Revoke a single workspace bearer."""
    await valkey.delete(f"{WORKSPACE_BEARER_KEY_PREFIX}{bearer}")


async def invalidate_all_workspace_bearers(valkey) -> int:
    """Revoke every issued workspace bearer (used when the workspace is disabled).

    Returns the number of bearers removed.
    """
    removed = 0
    pattern = f"{WORKSPACE_BEARER_KEY_PREFIX}*"
    try:
        async for key in valkey.scan_iter(match=pattern):
            await valkey.delete(key)
            removed += 1
    except Exception:
        logger.warning("invalidate_all_workspace_bearers: scan failed", exc_info=True)
    return removed


async def resolve_refresh_caller(valkey, bearer: str, task_bearer_prefix: str) -> str | None:
    """Return a caller identifier if `bearer` may call a refresh endpoint, else None.

    Accepted if the bearer is a live workspace bearer OR a live task-scoped bearer
    under `task_bearer_prefix`. A matching workspace bearer has its TTL renewed so
    an active gateway keeps its credential alive. Returns ``"workspace"`` for the
    gateway, or the stored task id for a task-scoped caller.
    """
    ws_key = f"{WORKSPACE_BEARER_KEY_PREFIX}{bearer}"
    ws = await valkey.get(ws_key)
    if ws is not None:
        await renew_workspace_bearer(valkey, bearer)
        return "workspace"

    stored = await valkey.get(f"{task_bearer_prefix}{bearer}")
    if stored is not None:
        return stored
    return None


_bearer_scheme = HTTPBearer(auto_error=False)


async def require_workspace_bearer(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer_scheme),
) -> str:
    """FastAPI dependency accepting ONLY a live workspace bearer.

    Used by gateway-only endpoints (e.g. health reporting). Task-scoped bearers
    are rejected — this is not a token-refresh endpoint.
    """
    if credentials is None or not credentials.credentials:
        raise HTTPException(status_code=401, detail="missing bearer token")

    valkey = get_valkey()
    if valkey is None:
        raise HTTPException(status_code=503, detail="Valkey unavailable")

    try:
        present = await valkey.get(f"{WORKSPACE_BEARER_KEY_PREFIX}{credentials.credentials}")
    except Exception:
        raise HTTPException(status_code=503, detail="Valkey unavailable")

    if present is None:
        raise HTTPException(status_code=401, detail="invalid or expired workspace bearer")
    await renew_workspace_bearer(valkey, credentials.credentials)
    return "workspace"


def require_refresh_bearer(task_bearer_prefix: str):
    """Build a FastAPI dependency guarding a token-refresh endpoint.

    The returned dependency authorizes the request iff the presented bearer is a
    live workspace bearer or a live task-scoped bearer under `task_bearer_prefix`.
    It returns the caller identifier (``"workspace"`` or a task id) for logging.
    """

    async def _dependency(
        credentials: HTTPAuthorizationCredentials | None = Depends(_bearer_scheme),
    ) -> str:
        if credentials is None or not credentials.credentials:
            raise HTTPException(status_code=401, detail="missing bearer token")

        valkey = get_valkey()
        if valkey is None:
            raise HTTPException(status_code=503, detail="Valkey unavailable")

        try:
            caller = await resolve_refresh_caller(
                valkey, credentials.credentials, task_bearer_prefix
            )
        except HTTPException:
            raise
        except Exception:
            raise HTTPException(status_code=503, detail="Valkey unavailable")

        if caller is None:
            raise HTTPException(status_code=401, detail="invalid or expired bearer token")
        return caller

    return _dependency
