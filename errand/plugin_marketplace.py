"""Plugin marketplace and plugin lifecycle for errand.

Provides:
  - Pydantic schemas for `.claude-plugin/marketplace.json` and `plugin.json`
  - A source-type-aware fetcher (`github` | `git` | `http` | `local`) used for
    both marketplaces and plugins
  - Marketplace sync (refresh `cached_manifest`, sync status)
  - Plugin install / update / uninstall against the on-disk cache layout
  - Helpers used by the task manager (skill discovery, MCP discovery)

Disk layout:
  /var/cache/errand/plugins/marketplaces/<name>/        marketplace clones / JSON
  /var/cache/errand/plugins/installed/<scope>/<plugin>/<version>/   plugin trees

`<scope>` = marketplace name for marketplace plugins, "manual" for direct installs.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import shutil
import subprocess
import tempfile
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal, Optional

import httpx
from pydantic import BaseModel, Field, ValidationError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models import Marketplace, Plugin
from platforms.credentials import decrypt as decrypt_blob, encrypt as encrypt_blob

logger = logging.getLogger(__name__)

CACHE_BASE = Path(os.environ.get("PLUGIN_CACHE_BASE", "/var/cache/errand/plugins"))
MARKETPLACE_CACHE = CACHE_BASE / "marketplaces"
INSTALLED_CACHE = CACHE_BASE / "installed"

# Per-plugin in-flight warm futures. Tasks can `await wait_for_plugin(pid)` to
# block until the eager startup warm (or a manual re-warm) for that plugin
# completes. A resolved future with result True means the cache is ready;
# False means the warm failed and the task should proceed without that plugin.
_warm_futures: dict[uuid.UUID, asyncio.Future] = {}
_warm_futures_lock: Optional[asyncio.Lock] = None


def _get_warm_lock() -> asyncio.Lock:
    global _warm_futures_lock
    if _warm_futures_lock is None:
        _warm_futures_lock = asyncio.Lock()
    return _warm_futures_lock


async def wait_for_plugin(plugin_id: uuid.UUID, timeout: float = 120.0) -> bool:
    """Block until plugin_id's cache is ready (or warm has failed). Returns
    True on success, False if the warm failed or timed out. If no warm has
    been registered, returns True immediately (plugin assumed already cached)."""
    fut = _warm_futures.get(plugin_id)
    if fut is None:
        return True
    try:
        return await asyncio.wait_for(asyncio.shield(fut), timeout=timeout)
    except (asyncio.TimeoutError, asyncio.CancelledError):
        return False
    except Exception:
        return False

IGNORED_ARTIFACT_DIRS = (
    "commands", "agents", "hooks", "lspServers", "themes", "output-styles",
    "monitors", "bin",
)


# --------------------------------------------------------------------------- #
# Schemas                                                                     #
# --------------------------------------------------------------------------- #


class PluginSourceObject(BaseModel):
    source: Optional[str] = None
    repo: Optional[str] = None
    url: Optional[str] = None
    ref: Optional[str] = None
    sha: Optional[str] = None
    path: Optional[str] = None
    package: Optional[str] = None  # npm — unsupported
    version: Optional[str] = None
    registry: Optional[str] = None


class MarketplacePluginEntry(BaseModel):
    name: str
    description: Optional[str] = None
    version: Optional[str] = None
    display_name: Optional[str] = Field(default=None, alias="displayName")
    keywords: list[str] = Field(default_factory=list)
    category: Optional[str] = None
    source: Any  # str | PluginSourceObject — normalized below

    model_config = {"populate_by_name": True}


class MarketplaceManifest(BaseModel):
    name: str
    owner: Optional[dict] = None
    description: Optional[str] = None
    version: Optional[str] = None
    plugins: list[MarketplacePluginEntry] = Field(default_factory=list)


class PluginManifest(BaseModel):
    name: str
    display_name: Optional[str] = Field(default=None, alias="displayName")
    version: Optional[str] = None
    description: Optional[str] = None
    skills: Any = None
    commands: Any = None
    agents: Any = None
    hooks: Any = None
    mcp_servers: Any = Field(default=None, alias="mcpServers")
    lsp_servers: Any = Field(default=None, alias="lspServers")

    model_config = {"populate_by_name": True, "extra": "allow"}


# --------------------------------------------------------------------------- #
# Source normalisation + fetcher                                              #
# --------------------------------------------------------------------------- #


@dataclass
class NormalizedSource:
    """Normalized form of a marketplace or plugin source descriptor."""
    kind: Literal["github", "git", "http", "local", "relative", "unsupported"]
    url: str = ""
    ref: Optional[str] = None
    path: Optional[str] = None  # for relative / git-subdir
    unsupported_reason: Optional[str] = None


def normalize_plugin_source(src: Any, marketplace_base: Optional[Path] = None) -> NormalizedSource:
    """Convert a `source` value from marketplace.json into a NormalizedSource."""
    if isinstance(src, str):
        if src.startswith("./") or src.startswith("../"):
            return NormalizedSource(kind="relative", path=src)
        if src.count("/") == 1 and "://" not in src:
            return NormalizedSource(kind="github", url=src)
        if src.startswith(("http://", "https://", "git@", "ssh://", "git://")):
            return NormalizedSource(kind="git", url=src)
        if os.path.isabs(src):
            return NormalizedSource(kind="local", url=src)
        return NormalizedSource(kind="relative", path=src)
    if isinstance(src, dict):
        try:
            obj = PluginSourceObject(**src)
        except ValidationError as exc:
            return NormalizedSource(kind="unsupported", unsupported_reason=str(exc))
        if obj.source == "github" and obj.repo:
            return NormalizedSource(kind="github", url=obj.repo, ref=obj.ref or obj.sha)
        if obj.source == "url" and obj.url:
            return NormalizedSource(kind="git", url=obj.url, ref=obj.ref or obj.sha)
        if obj.source == "git-subdir" and obj.url:
            return NormalizedSource(kind="git", url=obj.url, ref=obj.ref or obj.sha, path=obj.path)
        if obj.source == "npm":
            return NormalizedSource(kind="unsupported", unsupported_reason="npm sources not supported")
        if obj.path:
            return NormalizedSource(kind="relative", path=obj.path)
    return NormalizedSource(kind="unsupported", unsupported_reason=f"unrecognised source: {src!r}")


def _github_clone_url(short: str) -> str:
    return f"https://github.com/{short.split('#', 1)[0]}.git"


def _split_ref(maybe_with_ref: str, explicit_ref: Optional[str]) -> tuple[str, Optional[str]]:
    if explicit_ref:
        return maybe_with_ref, explicit_ref
    if "#" in maybe_with_ref:
        url, ref = maybe_with_ref.split("#", 1)
        return url, ref or None
    return maybe_with_ref, None


def _ssh_env(ssh_private_key: Optional[str], extra_env: Optional[dict] = None) -> tuple[dict, Optional[str]]:
    env = os.environ.copy()
    if extra_env:
        env.update(extra_env)
    key_file_path = None
    if ssh_private_key:
        key_file = tempfile.NamedTemporaryFile(mode="w", suffix=".key", delete=False)
        key_file.write(ssh_private_key)
        key_file.close()
        os.chmod(key_file.name, 0o600)
        env["GIT_SSH_COMMAND"] = f"ssh -i {key_file.name} -o StrictHostKeyChecking=accept-new"
        key_file_path = key_file.name
    return env, key_file_path


_ALLOWED_GIT_URL_PREFIXES = ("https://", "http://", "ssh://", "git://", "git@")


def _git_clone(url: str, ref: Optional[str], dest: Path, ssh_private_key: Optional[str]) -> None:
    """Shallow clone url@ref into dest (replacing existing).

    Validates url/ref to defend against argv flag smuggling: leading-dash values
    would otherwise be interpreted by git as options (e.g. --upload-pack).
    """
    if url.startswith("-") or (ref is not None and ref.startswith("-")):
        raise RuntimeError(f"refusing suspicious git argument: url={url!r} ref={ref!r}")
    if not any(url.startswith(p) for p in _ALLOWED_GIT_URL_PREFIXES):
        raise RuntimeError(
            f"refusing git URL with disallowed scheme: {url!r} "
            f"(allowed: {_ALLOWED_GIT_URL_PREFIXES})"
        )
    if dest.exists():
        shutil.rmtree(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    env, key_file = _ssh_env(ssh_private_key)
    try:
        cmd = ["git", "clone", "--depth", "1"]
        if ref:
            cmd += ["--branch", ref]
        cmd += ["--", url, str(dest)]
        result = subprocess.run(cmd, env=env, capture_output=True, text=True)
        if result.returncode != 0:
            err = (result.stderr or result.stdout or "").strip()
            raise RuntimeError(f"git clone failed: {err}")
    finally:
        if key_file:
            try:
                os.unlink(key_file)
            except OSError:
                pass


async def _http_fetch_json(url: str, bearer_token: Optional[str]) -> Any:
    headers = {}
    if bearer_token:
        headers["Authorization"] = f"Bearer {bearer_token}"
    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.get(url, headers=headers, follow_redirects=True)
        resp.raise_for_status()
        return resp.json()


# --------------------------------------------------------------------------- #
# Marketplace operations                                                      #
# --------------------------------------------------------------------------- #


class MarketplaceFetchError(Exception):
    """Raised when a marketplace cannot be fetched."""


@dataclass
class FetchedMarketplace:
    manifest: MarketplaceManifest
    base_dir: Optional[Path]  # populated for git-based sources; None for http
    raw: dict


async def fetch_marketplace(
    source_type: str,
    source_url: str,
    ref: Optional[str],
    bearer_token: Optional[str],
    ssh_private_key: Optional[str],
    cache_dir: Path,
) -> FetchedMarketplace:
    """Fetch and parse a marketplace manifest from any source type."""
    raw: dict
    base_dir: Optional[Path] = None
    if source_type == "github":
        url, effective_ref = _split_ref(source_url, ref)
        clone_url = _github_clone_url(url)
        await asyncio.to_thread(_git_clone, clone_url, effective_ref, cache_dir, ssh_private_key)
        base_dir = cache_dir
        manifest_path = base_dir / ".claude-plugin" / "marketplace.json"
        if not manifest_path.is_file():
            raise MarketplaceFetchError(
                f"marketplace.json not found at {manifest_path}",
            )
        raw = json.loads(manifest_path.read_text(encoding="utf-8"))
    elif source_type == "git":
        url, effective_ref = _split_ref(source_url, ref)
        await asyncio.to_thread(_git_clone, url, effective_ref, cache_dir, ssh_private_key)
        base_dir = cache_dir
        manifest_path = base_dir / ".claude-plugin" / "marketplace.json"
        if not manifest_path.is_file():
            raise MarketplaceFetchError(
                f"marketplace.json not found at {manifest_path}",
            )
        raw = json.loads(manifest_path.read_text(encoding="utf-8"))
    elif source_type == "http":
        try:
            raw = await _http_fetch_json(source_url, bearer_token)
        except httpx.HTTPError as exc:
            raise MarketplaceFetchError(f"http fetch failed: {exc}") from exc
    elif source_type == "local":
        local_path = Path(source_url)
        if local_path.is_dir():
            candidate = local_path / ".claude-plugin" / "marketplace.json"
            if not candidate.is_file():
                raise MarketplaceFetchError(f"marketplace.json not found under {local_path}")
            raw = json.loads(candidate.read_text(encoding="utf-8"))
            base_dir = local_path
        elif local_path.is_file():
            raw = json.loads(local_path.read_text(encoding="utf-8"))
        else:
            raise MarketplaceFetchError(f"local source not found: {source_url}")
    else:
        raise MarketplaceFetchError(f"unknown source_type: {source_type}")

    try:
        manifest = MarketplaceManifest.model_validate(raw)
    except ValidationError as exc:
        raise MarketplaceFetchError(f"manifest schema error: {exc}") from exc
    return FetchedMarketplace(manifest=manifest, base_dir=base_dir, raw=raw)


def marketplace_cache_dir(marketplace_name: str) -> Path:
    """Disk location for a marketplace's clone or downloaded manifest."""
    return MARKETPLACE_CACHE / _safe_segment(marketplace_name)


async def sync_marketplace(
    marketplace: Marketplace,
    session: AsyncSession,
    ssh_private_key: Optional[str] = None,
) -> None:
    """Refresh the marketplace's cached manifest and sync status fields."""
    from datetime import datetime, timezone

    bearer = None
    if marketplace.auth_token_encrypted:
        try:
            bearer = decrypt_blob(marketplace.auth_token_encrypted).get("token")
        except Exception:
            logger.warning("Failed to decrypt marketplace auth token for %s", marketplace.name)

    cache_dir = marketplace_cache_dir(marketplace.name)
    try:
        fetched = await fetch_marketplace(
            source_type=marketplace.source_type,
            source_url=marketplace.source_url,
            ref=marketplace.ref,
            bearer_token=bearer,
            ssh_private_key=ssh_private_key,
            cache_dir=cache_dir,
        )
        marketplace.cached_manifest = fetched.raw
        marketplace.last_sync_status = "ok"
        marketplace.last_sync_error = None
    except MarketplaceFetchError as exc:
        marketplace.last_sync_status = "error"
        marketplace.last_sync_error = str(exc)
        logger.warning("Sync failed for marketplace %s: %s", marketplace.name, exc)
    except Exception as exc:  # noqa: BLE001
        marketplace.last_sync_status = "error"
        marketplace.last_sync_error = f"unexpected: {exc}"
        logger.exception("Unexpected sync failure for marketplace %s", marketplace.name)
    finally:
        marketplace.last_synced_at = datetime.now(timezone.utc)
        await session.flush()


# --------------------------------------------------------------------------- #
# Plugin operations                                                           #
# --------------------------------------------------------------------------- #


class PluginInstallError(Exception):
    """Raised when a plugin cannot be installed."""


def _safe_segment(name: str) -> str:
    """Normalize a name for use as a path segment."""
    return name.replace("/", "_").replace("..", "_")


def plugin_install_dir(scope: str, plugin_name: str, version: str) -> Path:
    return INSTALLED_CACHE / _safe_segment(scope) / _safe_segment(plugin_name) / _safe_segment(version)


def _detect_plugin_root(candidate: Path) -> Path:
    """Given a candidate directory, locate the plugin root (containing
    .claude-plugin/plugin.json or skills/.mcp.json)."""
    if (candidate / ".claude-plugin" / "plugin.json").is_file():
        return candidate
    if (candidate / "skills").is_dir() or (candidate / ".mcp.json").is_file():
        return candidate
    for child in candidate.iterdir():
        if child.is_dir():
            if (child / ".claude-plugin" / "plugin.json").is_file() or (child / "skills").is_dir() or (child / ".mcp.json").is_file():
                return child
    return candidate


def _read_plugin_manifest(plugin_root: Path) -> Optional[PluginManifest]:
    manifest_path = plugin_root / ".claude-plugin" / "plugin.json"
    if not manifest_path.is_file():
        return None
    try:
        raw = json.loads(manifest_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise PluginInstallError(f"plugin.json malformed: {exc}") from exc
    try:
        return PluginManifest.model_validate(raw)
    except ValidationError as exc:
        raise PluginInstallError(f"plugin.json schema error: {exc}") from exc


def _count_ignored_artifacts(plugin_root: Path) -> list[dict]:
    """Walk the plugin tree counting artifact kinds errand does not consume."""
    out: list[dict] = []
    for kind in IGNORED_ARTIFACT_DIRS:
        target = plugin_root / kind
        if target.is_dir():
            count = sum(1 for p in target.rglob("*") if p.is_file())
            if count:
                out.append({"type": kind, "count": count})
    return out


async def install_plugin(
    *,
    session: AsyncSession,
    marketplace: Optional[Marketplace],
    plugin_name: str,
    version: Optional[str] = None,
    direct_source_type: Optional[str] = None,
    direct_source_url: Optional[str] = None,
    direct_ref: Optional[str] = None,
    direct_bearer_token: Optional[str] = None,
    ssh_private_key: Optional[str] = None,
) -> Plugin:
    """Install a plugin from a marketplace OR a direct source descriptor.

    Returns the persisted Plugin row (with enabled=false by default).
    """
    if marketplace is not None:
        entry = _resolve_marketplace_plugin(marketplace, plugin_name)
        if entry is None:
            raise PluginInstallError(
                f"plugin '{plugin_name}' not found in marketplace '{marketplace.name}'",
            )
        resolved = normalize_plugin_source(
            entry.source,
            marketplace_base=marketplace_cache_dir(marketplace.name),
        )
        if resolved.kind == "unsupported":
            raise PluginInstallError(
                f"plugin source unsupported: {resolved.unsupported_reason}",
            )
        effective_version = version or entry.version or "latest"
        scope = marketplace.name
        bearer = None
        if marketplace.auth_token_encrypted:
            try:
                bearer = decrypt_blob(marketplace.auth_token_encrypted).get("token")
            except Exception:
                logger.warning("Failed to decrypt marketplace token for install")
    else:
        if not direct_source_type or not direct_source_url:
            raise PluginInstallError("direct install requires source_type and source_url")
        resolved = NormalizedSource(
            kind=direct_source_type,  # type: ignore[arg-type]
            url=direct_source_url,
            ref=direct_ref,
        )
        if resolved.kind not in ("github", "git", "http", "local"):
            raise PluginInstallError(f"unsupported direct source_type: {direct_source_type}")
        effective_version = version or direct_ref or "latest"
        scope = "manual"
        bearer = direct_bearer_token

    install_dir = plugin_install_dir(scope, plugin_name, effective_version)
    await _fetch_plugin_into(resolved, install_dir, bearer, ssh_private_key, marketplace)
    plugin_root = _detect_plugin_root(install_dir)
    plugin_json = _read_plugin_manifest(plugin_root)

    ignored = _count_ignored_artifacts(plugin_root)
    if ignored:
        logger.info(
            "Plugin '%s@%s' contains artifacts errand will ignore: %s",
            plugin_name, effective_version,
            ", ".join(f"{a['type']} ({a['count']})" for a in ignored),
        )

    encrypted_token = None
    if direct_bearer_token and marketplace is None:
        encrypted_token = encrypt_blob({"token": direct_bearer_token})

    plugin = Plugin(
        id=uuid.uuid4(),
        marketplace_id=marketplace.id if marketplace else None,
        plugin_name=plugin_name,
        source_type=None if marketplace else resolved.kind,
        source_url=None if marketplace else resolved.url,
        ref=None if marketplace else resolved.ref,
        auth_token_encrypted=encrypted_token,
        installed_version=effective_version,
        latest_available_version=effective_version,
        enabled=False,
        manifest=plugin_json.model_dump(by_alias=True) if plugin_json else None,
        ignored_artifacts=ignored or None,
        skill_conflicts=None,
    )
    session.add(plugin)
    await session.flush()
    return plugin


def _resolve_marketplace_plugin(
    marketplace: Marketplace, plugin_name: str,
) -> Optional[MarketplacePluginEntry]:
    raw = marketplace.cached_manifest
    if not raw:
        return None
    try:
        manifest = MarketplaceManifest.model_validate(raw)
    except ValidationError:
        return None
    for entry in manifest.plugins:
        if entry.name == plugin_name:
            return entry
    return None


async def _fetch_plugin_into(
    source: NormalizedSource,
    dest: Path,
    bearer_token: Optional[str],
    ssh_private_key: Optional[str],
    marketplace: Optional[Marketplace],
) -> None:
    """Materialize the plugin's source tree into `dest`."""
    if dest.exists():
        shutil.rmtree(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)

    if source.kind == "github":
        clone_url = _github_clone_url(source.url)
        await asyncio.to_thread(_git_clone, clone_url, source.ref, dest, ssh_private_key)
        return
    if source.kind == "git":
        await asyncio.to_thread(_git_clone, source.url, source.ref, dest, ssh_private_key)
        if source.path:
            sub = dest / source.path
            if sub.is_dir():
                tmp = dest.parent / (dest.name + ".tmp")
                shutil.move(str(sub), str(tmp))
                shutil.rmtree(dest)
                shutil.move(str(tmp), str(dest))
        return
    if source.kind == "http":
        async with httpx.AsyncClient(timeout=60.0) as client:
            headers = {"Authorization": f"Bearer {bearer_token}"} if bearer_token else {}
            resp = await client.get(source.url, headers=headers, follow_redirects=True)
            resp.raise_for_status()
            dest.mkdir(parents=True)
            (dest / ".claude-plugin").mkdir()
            (dest / ".claude-plugin" / "plugin.json").write_bytes(resp.content)
        return
    if source.kind == "local":
        src_path = Path(source.url)
        if not src_path.exists():
            raise PluginInstallError(f"local plugin path missing: {src_path}")
        if src_path.is_dir():
            shutil.copytree(src_path, dest)
        else:
            dest.mkdir(parents=True)
            shutil.copy(src_path, dest / src_path.name)
        return
    if source.kind == "relative":
        if not marketplace:
            raise PluginInstallError("relative plugin source requires a marketplace context")
        if source.path and ".." in Path(source.path).parts:
            raise PluginInstallError(
                f"relative plugin path may not contain '..' segments: {source.path!r}"
            )
        if marketplace.source_type == "local":
            base = Path(marketplace.source_url)
        else:
            base = marketplace_cache_dir(marketplace.name)
        base_resolved = base.resolve()
        sub = (base_resolved / source.path).resolve() if source.path else base_resolved
        try:
            sub.relative_to(base_resolved)
        except ValueError:
            raise PluginInstallError(
                f"relative plugin path escapes marketplace base: {source.path!r}"
            )
        if not sub.is_dir():
            raise PluginInstallError(f"relative plugin path does not exist: {sub}")
        shutil.copytree(sub, dest, symlinks=False)
        return
    raise PluginInstallError(f"unsupported plugin source: {source.kind}")


async def update_plugin(
    plugin: Plugin,
    session: AsyncSession,
    ssh_private_key: Optional[str] = None,
) -> None:
    """Re-fetch the plugin at `latest_available_version`, swap on disk, bump installed_version."""
    if not plugin.latest_available_version or plugin.latest_available_version == plugin.installed_version:
        return

    new_version = plugin.latest_available_version
    scope = "manual"
    marketplace: Optional[Marketplace] = None
    if plugin.marketplace_id is not None:
        marketplace = await session.get(Marketplace, plugin.marketplace_id)
        if marketplace is None:
            raise PluginInstallError("plugin's marketplace no longer exists")
        scope = marketplace.name

    if marketplace is not None:
        entry = _resolve_marketplace_plugin(marketplace, plugin.plugin_name)
        if entry is None:
            raise PluginInstallError("plugin no longer in marketplace manifest")
        resolved = normalize_plugin_source(
            entry.source, marketplace_base=marketplace_cache_dir(marketplace.name),
        )
        bearer = None
        if marketplace.auth_token_encrypted:
            try:
                bearer = decrypt_blob(marketplace.auth_token_encrypted).get("token")
            except Exception:
                pass
    else:
        resolved = NormalizedSource(
            kind=plugin.source_type,  # type: ignore[arg-type]
            url=plugin.source_url or "",
            ref=new_version,
        )
        bearer = None
        if plugin.auth_token_encrypted:
            try:
                bearer = decrypt_blob(plugin.auth_token_encrypted).get("token")
            except Exception:
                pass

    new_dir = plugin_install_dir(scope, plugin.plugin_name, new_version)
    await _fetch_plugin_into(resolved, new_dir, bearer, ssh_private_key, marketplace)
    plugin_root = _detect_plugin_root(new_dir)
    plugin_json = _read_plugin_manifest(plugin_root)
    ignored = _count_ignored_artifacts(plugin_root)

    old_dir = plugin_install_dir(scope, plugin.plugin_name, plugin.installed_version)
    plugin.installed_version = new_version
    plugin.manifest = plugin_json.model_dump(by_alias=True) if plugin_json else None
    plugin.ignored_artifacts = ignored or None
    if old_dir.exists() and old_dir != new_dir:
        shutil.rmtree(old_dir, ignore_errors=True)
    await session.flush()


async def uninstall_plugin(plugin: Plugin, session: AsyncSession) -> None:
    """Remove the plugin row and its on-disk cache."""
    scope = "manual"
    if plugin.marketplace_id is not None:
        mp = await session.get(Marketplace, plugin.marketplace_id)
        if mp is not None:
            scope = mp.name
    install_dir = plugin_install_dir(scope, plugin.plugin_name, plugin.installed_version)
    if install_dir.exists():
        shutil.rmtree(install_dir, ignore_errors=True)
    await session.delete(plugin)


# --------------------------------------------------------------------------- #
# Skill + MCP discovery on installed plugins                                  #
# --------------------------------------------------------------------------- #


def parse_plugin_skills(plugin: Plugin, scope: str) -> list[dict]:
    """Walk a plugin's skills/ directory using the existing parser shape."""
    # Imported lazily to avoid a circular import on task_manager.
    from task_manager import parse_skills_from_directory

    install_dir = plugin_install_dir(scope, plugin.plugin_name, plugin.installed_version)
    plugin_root = _detect_plugin_root(install_dir)
    skills_dir = plugin_root / "skills"
    if not skills_dir.is_dir():
        return []
    return parse_skills_from_directory(str(skills_dir))


def parse_plugin_mcp_servers(plugin: Plugin, scope: str) -> dict[str, dict]:
    """Return the plugin's raw MCP server map (un-namespaced)."""
    install_dir = plugin_install_dir(scope, plugin.plugin_name, plugin.installed_version)
    plugin_root = _detect_plugin_root(install_dir)
    inline: Optional[dict] = None
    plugin_json_path = plugin_root / ".claude-plugin" / "plugin.json"
    if plugin_json_path.is_file():
        try:
            raw = json.loads(plugin_json_path.read_text(encoding="utf-8"))
            if isinstance(raw.get("mcpServers"), dict):
                inline = raw["mcpServers"]
        except json.JSONDecodeError:
            pass
    if inline is not None:
        return inline
    mcp_json_path = plugin_root / ".mcp.json"
    if mcp_json_path.is_file():
        try:
            raw = json.loads(mcp_json_path.read_text(encoding="utf-8"))
            if isinstance(raw, dict):
                if "mcpServers" in raw and isinstance(raw["mcpServers"], dict):
                    return raw["mcpServers"]
                return raw
        except json.JSONDecodeError:
            pass
    return {}


def namespaced_mcp_servers(plugin: Plugin, scope: str) -> dict[str, dict]:
    """Return the plugin's MCP servers with names prefixed `<plugin_name>__`."""
    raw = parse_plugin_mcp_servers(plugin, scope)
    return {f"{plugin.plugin_name}__{name}": cfg for name, cfg in raw.items()}


# --------------------------------------------------------------------------- #
# Cache warm                                                                  #
# --------------------------------------------------------------------------- #


def ensure_cache_layout() -> None:
    MARKETPLACE_CACHE.mkdir(parents=True, exist_ok=True)
    INSTALLED_CACHE.mkdir(parents=True, exist_ok=True)


async def warm_plugin_caches(
    session: AsyncSession,
    ssh_private_key: Optional[str] = None,
    concurrency: int = 4,
) -> None:
    """Eagerly fetch enabled plugins missing from disk in parallel."""
    ensure_cache_layout()
    result = await session.execute(select(Plugin).where(Plugin.enabled.is_(True)))
    plugins = list(result.scalars())
    if not plugins:
        return
    sem = asyncio.Semaphore(concurrency)
    loop = asyncio.get_event_loop()

    async with _get_warm_lock():
        for plugin in plugins:
            if plugin.id not in _warm_futures or _warm_futures[plugin.id].done():
                _warm_futures[plugin.id] = loop.create_future()

    async def warm(plugin: Plugin) -> None:
        fut = _warm_futures.get(plugin.id)
        async with sem:
            scope = "manual"
            marketplace = None
            if plugin.marketplace_id is not None:
                marketplace = await session.get(Marketplace, plugin.marketplace_id)
                if marketplace is not None:
                    scope = marketplace.name
            install_dir = plugin_install_dir(scope, plugin.plugin_name, plugin.installed_version)
            if install_dir.exists() and any(install_dir.iterdir()):
                if fut is not None and not fut.done():
                    fut.set_result(True)
                return
            try:
                if marketplace is not None:
                    entry = _resolve_marketplace_plugin(marketplace, plugin.plugin_name)
                    if entry is None:
                        logger.warning(
                            "Plugin %s no longer in marketplace %s manifest; skipping warm",
                            plugin.plugin_name, marketplace.name,
                        )
                        return
                    resolved = normalize_plugin_source(
                        entry.source, marketplace_base=marketplace_cache_dir(marketplace.name),
                    )
                    bearer = None
                    if marketplace.auth_token_encrypted:
                        try:
                            bearer = decrypt_blob(marketplace.auth_token_encrypted).get("token")
                        except Exception:
                            pass
                else:
                    resolved = NormalizedSource(
                        kind=plugin.source_type,  # type: ignore[arg-type]
                        url=plugin.source_url or "",
                        ref=plugin.ref,
                    )
                    bearer = None
                    if plugin.auth_token_encrypted:
                        try:
                            bearer = decrypt_blob(plugin.auth_token_encrypted).get("token")
                        except Exception:
                            pass
                await _fetch_plugin_into(resolved, install_dir, bearer, ssh_private_key, marketplace)
                logger.info("Warmed plugin cache for %s@%s", plugin.plugin_name, plugin.installed_version)
                if fut is not None and not fut.done():
                    fut.set_result(True)
            except Exception:
                logger.exception("Failed to warm plugin cache for %s", plugin.plugin_name)
                if fut is not None and not fut.done():
                    fut.set_result(False)

    await asyncio.gather(*(warm(p) for p in plugins))


# --------------------------------------------------------------------------- #
# Helpers                                                                     #
# --------------------------------------------------------------------------- #


def update_latest_versions_from_manifest(
    marketplace: Marketplace, plugins: list[Plugin],
) -> list[Plugin]:
    """Update each plugin row's `latest_available_version` based on the marketplace manifest.

    Returns the list of plugin rows whose latest_available_version changed.
    """
    raw = marketplace.cached_manifest
    if not raw:
        return []
    try:
        manifest = MarketplaceManifest.model_validate(raw)
    except ValidationError:
        return []
    by_name = {entry.name: entry for entry in manifest.plugins}
    from datetime import datetime, timezone
    changed: list[Plugin] = []
    for plugin in plugins:
        entry = by_name.get(plugin.plugin_name)
        plugin.last_checked_at = datetime.now(timezone.utc)
        if entry is None:
            continue
        latest = entry.version
        if latest and latest != plugin.latest_available_version:
            plugin.latest_available_version = latest
            changed.append(plugin)
    return changed


async def run_marketplace_poller(
    session_factory,
    get_interval_seconds,
    get_ssh_private_key,
) -> None:
    """Background poller that periodically re-syncs enabled marketplaces and
    refreshes `latest_available_version` on installed plugins.

    `session_factory` must be a callable returning a new AsyncSession context manager.
    `get_interval_seconds` is a callable returning the current poll interval; the
    poller skips the body when the value is 0 (disabled).
    `get_ssh_private_key` is an async callable returning the SSH private key string
    or None.
    """
    while True:
        try:
            interval = int(await _maybe_await(get_interval_seconds))
        except Exception:
            interval = 21600
        if interval <= 0:
            await asyncio.sleep(60)  # cheap idle when disabled
            continue
        try:
            async with session_factory() as session:
                ssh_key = await _maybe_await(get_ssh_private_key)
                result = await session.execute(
                    select(Marketplace).where(Marketplace.enabled.is_(True))
                )
                marketplaces = list(result.scalars())
                for mp in marketplaces:
                    try:
                        await sync_marketplace(mp, session, ssh_private_key=ssh_key)
                        plugin_result = await session.execute(
                            select(Plugin).where(Plugin.marketplace_id == mp.id)
                        )
                        plugins = list(plugin_result.scalars())
                        update_latest_versions_from_manifest(mp, plugins)
                    except Exception:
                        logger.exception(
                            "Poller: marketplace %s sync failed", mp.name,
                        )
                await session.commit()
        except Exception:
            logger.exception("Marketplace poller loop iteration failed")
        await asyncio.sleep(interval)


async def _maybe_await(value):
    if asyncio.iscoroutine(value):
        return await value
    if callable(value):
        out = value()
        if asyncio.iscoroutine(out):
            return await out
        return out
    return value


@dataclass
class PluginScope:
    """Resolved scope info for a plugin (marketplace name or 'manual')."""
    plugin: Plugin
    scope: str
    marketplace: Optional[Marketplace] = None


async def resolve_plugin_scopes(
    session: AsyncSession, plugins: list[Plugin],
) -> list[PluginScope]:
    """Hydrate marketplace references for a list of plugins to determine cache scope."""
    out: list[PluginScope] = []
    mp_ids = {p.marketplace_id for p in plugins if p.marketplace_id is not None}
    marketplaces: dict[uuid.UUID, Marketplace] = {}
    if mp_ids:
        result = await session.execute(select(Marketplace).where(Marketplace.id.in_(mp_ids)))
        for mp in result.scalars():
            marketplaces[mp.id] = mp
    for plugin in plugins:
        if plugin.marketplace_id is not None and plugin.marketplace_id in marketplaces:
            mp = marketplaces[plugin.marketplace_id]
            out.append(PluginScope(plugin=plugin, scope=mp.name, marketplace=mp))
        else:
            out.append(PluginScope(plugin=plugin, scope="manual"))
    return out
