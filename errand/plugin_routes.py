"""REST endpoints for plugin marketplaces and plugins.

Admin-only. All routes live under /api/marketplaces and /api/plugins.
"""

from __future__ import annotations

import logging
import uuid
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field, ValidationError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_session
from models import Marketplace, Plugin, Setting
from platforms.credentials import encrypt as encrypt_blob
from plugin_marketplace import (
    MarketplaceManifest,
    PluginInstallError,
    install_plugin,
    parse_plugin_mcp_servers,
    parse_plugin_skills,
    resolve_plugin_scopes,
    sync_marketplace,
    uninstall_plugin,
    update_latest_versions_from_manifest,
    update_plugin,
)

logger = logging.getLogger(__name__)


async def _require_admin(request: Request):
    """Auth dependency — late import to avoid circular import with main.py."""
    from main import require_admin
    from fastapi.security import HTTPBearer
    security = HTTPBearer(auto_error=True)
    credentials = await security(request)
    return await require_admin(request, credentials)


marketplaces_router = APIRouter(prefix="/api/marketplaces", tags=["marketplaces"])
plugins_router = APIRouter(prefix="/api/plugins", tags=["plugins"])


VALID_SOURCE_TYPES = {"github", "git", "http", "local"}


class MarketplaceCreate(BaseModel):
    name: str = Field(..., min_length=1)
    source_type: str
    source_url: str = Field(..., min_length=1)
    ref: Optional[str] = None
    auth_token: Optional[str] = None
    auth_credential_id: Optional[str] = None  # alias for auth_token (frontend convention)


class MarketplacePatch(BaseModel):
    enabled: Optional[bool] = None
    name: Optional[str] = None
    source_url: Optional[str] = None
    ref: Optional[str] = None
    auth_token: Optional[str] = None
    auth_credential_id: Optional[str] = None  # alias for auth_token (frontend convention)


class PluginInstallRequest(BaseModel):
    # From marketplace
    marketplace_id: Optional[uuid.UUID] = None
    plugin_name: Optional[str] = None
    version: Optional[str] = None
    # OR direct
    source_type: Optional[str] = None
    source_url: Optional[str] = None
    ref: Optional[str] = None
    auth_token: Optional[str] = None
    auth_credential_id: Optional[str] = None  # alias for auth_token (frontend convention)


class PluginPatch(BaseModel):
    enabled: Optional[bool] = None


async def _get_ssh_private_key(session: AsyncSession) -> Optional[str]:
    result = await session.execute(select(Setting).where(Setting.key == "ssh_private_key"))
    row = result.scalar_one_or_none()
    return row.value if row else None


def _serialize_marketplace(mp: Marketplace) -> dict:
    plugin_count = 0
    if isinstance(mp.cached_manifest, dict):
        try:
            plugin_count = len(MarketplaceManifest.model_validate(mp.cached_manifest).plugins)
        except ValidationError:
            plugin_count = 0
    return {
        "id": str(mp.id),
        "name": mp.name,
        "source_type": mp.source_type,
        "source_url": mp.source_url,
        "ref": mp.ref,
        "enabled": mp.enabled,
        "predefined": mp.predefined,
        "has_auth_token": bool(mp.auth_token_encrypted),
        "auth_credential_id": "***" if mp.auth_token_encrypted else None,
        "last_synced_at": mp.last_synced_at.isoformat() if mp.last_synced_at else None,
        "last_sync_status": mp.last_sync_status,
        "last_sync_error": mp.last_sync_error,
        "plugin_count": plugin_count,
    }


def _serialize_plugin(plugin: Plugin, scope: str) -> dict:
    # Always parse — the API surfaces what a plugin would contribute even when
    # disabled so admins can review before enabling.
    skills = parse_plugin_skills(plugin, scope)
    skill_names = [s["name"] for s in skills]
    raw_mcps = parse_plugin_mcp_servers(plugin, scope)
    mcp_pairs = [
        {"raw": name, "namespaced": f"{plugin.plugin_name}__{name}"}
        for name in raw_mcps.keys()
    ]
    update_available = (
        plugin.latest_available_version is not None
        and plugin.latest_available_version != plugin.installed_version
    )
    return {
        "id": str(plugin.id),
        "plugin_name": plugin.plugin_name,
        "marketplace_id": str(plugin.marketplace_id) if plugin.marketplace_id else None,
        "installed_version": plugin.installed_version,
        "latest_available_version": plugin.latest_available_version,
        "enabled": plugin.enabled,
        "update_available": update_available,
        "skills": skill_names,
        "mcp_servers": mcp_pairs,
        "ignored_artifacts": plugin.ignored_artifacts or [],
        "skill_conflicts": plugin.skill_conflicts or [],
        "manifest": plugin.manifest,
        "installed_at": plugin.installed_at.isoformat() if plugin.installed_at else None,
        "last_checked_at": plugin.last_checked_at.isoformat() if plugin.last_checked_at else None,
    }


# --------------------------------------------------------------------------- #
# Marketplaces                                                                #
# --------------------------------------------------------------------------- #


@marketplaces_router.get("")
async def list_marketplaces(
    session: AsyncSession = Depends(get_session),
    _user: dict = Depends(_require_admin),
) -> list[dict]:
    result = await session.execute(select(Marketplace).order_by(Marketplace.name))
    return [_serialize_marketplace(mp) for mp in result.scalars()]


@marketplaces_router.post("")
async def create_marketplace(
    body: MarketplaceCreate,
    session: AsyncSession = Depends(get_session),
    _user: dict = Depends(_require_admin),
) -> dict:
    if body.source_type not in VALID_SOURCE_TYPES:
        raise HTTPException(status_code=422, detail=f"invalid source_type; must be one of {sorted(VALID_SOURCE_TYPES)}")
    existing = await session.execute(select(Marketplace).where(Marketplace.name == body.name))
    if existing.scalar_one_or_none() is not None:
        raise HTTPException(status_code=409, detail=f"marketplace '{body.name}' already exists")

    token_value = body.auth_token or body.auth_credential_id
    mp = Marketplace(
        id=uuid.uuid4(),
        name=body.name,
        source_type=body.source_type,
        source_url=body.source_url,
        ref=body.ref,
        auth_token_encrypted=encrypt_blob({"token": token_value}) if token_value else None,
        enabled=True,
        predefined=False,
    )
    session.add(mp)
    await session.flush()
    try:
        ssh_key = await _get_ssh_private_key(session)
        await sync_marketplace(mp, session, ssh_private_key=ssh_key)
    except Exception:
        logger.exception("Initial sync failed for new marketplace %s", body.name)
    await session.commit()
    return _serialize_marketplace(mp)


@marketplaces_router.patch("/{marketplace_id}")
async def patch_marketplace(
    marketplace_id: uuid.UUID,
    body: MarketplacePatch,
    session: AsyncSession = Depends(get_session),
    _user: dict = Depends(_require_admin),
) -> dict:
    mp = await session.get(Marketplace, marketplace_id)
    if mp is None:
        raise HTTPException(status_code=404, detail="marketplace not found")

    # Use model_fields_set so explicit `null` clears a field while omission leaves
    # it unchanged. Without this, `null` and "field omitted" both surface as None.
    fields_set = body.model_fields_set
    needs_resync = False
    if "enabled" in fields_set and body.enabled is not None:
        mp.enabled = body.enabled
    if "name" in fields_set and body.name is not None and body.name != mp.name:
        existing = await session.execute(select(Marketplace).where(Marketplace.name == body.name))
        if existing.scalar_one_or_none() is not None:
            raise HTTPException(status_code=409, detail="name already in use")
        mp.name = body.name
    if "source_url" in fields_set and body.source_url is not None and body.source_url != mp.source_url:
        mp.source_url = body.source_url
        needs_resync = True
    if "ref" in fields_set:
        new_ref = body.ref or None  # explicit null or empty string clears the ref
        if new_ref != mp.ref:
            mp.ref = new_ref
            needs_resync = True
    if "auth_token" in fields_set or "auth_credential_id" in fields_set:
        token_value = body.auth_token if "auth_token" in fields_set else body.auth_credential_id
        mp.auth_token_encrypted = (
            encrypt_blob({"token": token_value}) if token_value else None
        )
        needs_resync = True
    await session.flush()
    if needs_resync:
        try:
            ssh_key = await _get_ssh_private_key(session)
            await sync_marketplace(mp, session, ssh_private_key=ssh_key)
        except Exception:
            logger.exception("Resync after PATCH failed for %s", mp.name)
    await session.commit()
    return _serialize_marketplace(mp)


@marketplaces_router.delete("/{marketplace_id}", status_code=204)
async def delete_marketplace(
    marketplace_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    _user: dict = Depends(_require_admin),
) -> None:
    mp = await session.get(Marketplace, marketplace_id)
    if mp is None:
        raise HTTPException(status_code=404, detail="marketplace not found")
    if mp.predefined:
        raise HTTPException(status_code=409, detail="predefined marketplaces cannot be deleted")
    await session.delete(mp)
    await session.commit()


@marketplaces_router.post("/{marketplace_id}/resync", status_code=202)
async def resync_marketplace(
    marketplace_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    _user: dict = Depends(_require_admin),
) -> dict:
    mp = await session.get(Marketplace, marketplace_id)
    if mp is None:
        raise HTTPException(status_code=404, detail="marketplace not found")
    ssh_key = await _get_ssh_private_key(session)
    await sync_marketplace(mp, session, ssh_private_key=ssh_key)
    plugin_result = await session.execute(
        select(Plugin).where(Plugin.marketplace_id == mp.id)
    )
    plugins = list(plugin_result.scalars())
    update_latest_versions_from_manifest(mp, plugins)
    await session.commit()
    return _serialize_marketplace(mp)


@marketplaces_router.get("/{marketplace_id}/plugins")
async def list_marketplace_plugins(
    marketplace_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    _user: dict = Depends(_require_admin),
) -> list[dict]:
    mp = await session.get(Marketplace, marketplace_id)
    if mp is None:
        raise HTTPException(status_code=404, detail="marketplace not found")
    if not isinstance(mp.cached_manifest, dict):
        return []
    try:
        manifest = MarketplaceManifest.model_validate(mp.cached_manifest)
    except ValidationError:
        return []
    out: list[dict] = []
    from plugin_marketplace import normalize_plugin_source
    for entry in manifest.plugins:
        norm = normalize_plugin_source(entry.source)
        out.append({
            "name": entry.name,
            "description": entry.description,
            "version": entry.version,
            "display_name": entry.display_name,
            "keywords": entry.keywords,
            "category": entry.category,
            "source_kind": norm.kind,
            "unsupported": norm.kind == "unsupported",
            "unsupported_reason": norm.unsupported_reason,
        })
    return out


# --------------------------------------------------------------------------- #
# Plugins                                                                     #
# --------------------------------------------------------------------------- #


@plugins_router.get("")
async def list_plugins(
    session: AsyncSession = Depends(get_session),
    _user: dict = Depends(_require_admin),
) -> list[dict]:
    result = await session.execute(select(Plugin).order_by(Plugin.plugin_name))
    plugins = list(result.scalars())
    scopes = await resolve_plugin_scopes(session, plugins)
    return [_serialize_plugin(s.plugin, s.scope) for s in scopes]


@plugins_router.post("")
async def install_plugin_endpoint(
    body: PluginInstallRequest,
    session: AsyncSession = Depends(get_session),
    _user: dict = Depends(_require_admin),
) -> dict:
    ssh_key = await _get_ssh_private_key(session)
    marketplace: Optional[Marketplace] = None
    if body.marketplace_id is not None:
        marketplace = await session.get(Marketplace, body.marketplace_id)
        if marketplace is None:
            raise HTTPException(status_code=404, detail="marketplace not found")
        if not body.plugin_name:
            raise HTTPException(status_code=422, detail="plugin_name required for marketplace install")
        plugin_name = body.plugin_name
    else:
        if not body.source_type or not body.source_url:
            raise HTTPException(status_code=422, detail="direct install requires source_type and source_url")
        if body.source_type not in VALID_SOURCE_TYPES:
            raise HTTPException(status_code=422, detail=f"invalid source_type")
        plugin_name = body.plugin_name or body.source_url.rstrip("/").split("/")[-1]
    try:
        plugin = await install_plugin(
            session=session,
            marketplace=marketplace,
            plugin_name=plugin_name,
            version=body.version,
            direct_source_type=body.source_type,
            direct_source_url=body.source_url,
            direct_ref=body.ref,
            direct_bearer_token=body.auth_token or body.auth_credential_id,
            ssh_private_key=ssh_key,
        )
    except PluginInstallError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    await session.commit()
    scope = marketplace.name if marketplace else "manual"
    return _serialize_plugin(plugin, scope)


@plugins_router.patch("/{plugin_id}")
async def patch_plugin(
    plugin_id: uuid.UUID,
    body: PluginPatch,
    session: AsyncSession = Depends(get_session),
    _user: dict = Depends(_require_admin),
) -> dict:
    plugin = await session.get(Plugin, plugin_id)
    if plugin is None:
        raise HTTPException(status_code=404, detail="plugin not found")
    if body.enabled is not None:
        plugin.enabled = body.enabled
    await session.commit()
    scopes = await resolve_plugin_scopes(session, [plugin])
    return _serialize_plugin(plugin, scopes[0].scope)


@plugins_router.post("/{plugin_id}/update")
async def update_plugin_endpoint(
    plugin_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    _user: dict = Depends(_require_admin),
) -> dict:
    plugin = await session.get(Plugin, plugin_id)
    if plugin is None:
        raise HTTPException(status_code=404, detail="plugin not found")
    ssh_key = await _get_ssh_private_key(session)
    try:
        await update_plugin(plugin, session, ssh_private_key=ssh_key)
    except PluginInstallError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    await session.commit()
    scopes = await resolve_plugin_scopes(session, [plugin])
    return _serialize_plugin(plugin, scopes[0].scope)


@plugins_router.delete("/{plugin_id}", status_code=204)
async def delete_plugin(
    plugin_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    _user: dict = Depends(_require_admin),
) -> None:
    plugin = await session.get(Plugin, plugin_id)
    if plugin is None:
        raise HTTPException(status_code=404, detail="plugin not found")
    await uninstall_plugin(plugin, session)
    await session.commit()
