"""Unit tests for plugin_marketplace module — source normalisation, parsing,
sync state transitions, install / update / uninstall against a tmpdir cache.
"""

from __future__ import annotations

import asyncio
import json
import os
import uuid
from pathlib import Path

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker

from models import Marketplace, Plugin


@pytest_asyncio.fixture
async def session(tmp_path, monkeypatch) -> AsyncSession:
    from tests.conftest import _create_tables
    monkeypatch.setenv("PLUGIN_CACHE_BASE", str(tmp_path / "cache"))
    monkeypatch.setenv("CREDENTIAL_ENCRYPTION_KEY", "9hH-fpyt0HRP4_g-Tt2j6_FzJD9Vqz2vIo5SXmlAEHE=")
    import plugin_marketplace
    plugin_marketplace.CACHE_BASE = Path(os.environ["PLUGIN_CACHE_BASE"])
    plugin_marketplace.MARKETPLACE_CACHE = plugin_marketplace.CACHE_BASE / "marketplaces"
    plugin_marketplace.INSTALLED_CACHE = plugin_marketplace.CACHE_BASE / "installed"

    engine = create_async_engine("sqlite+aiosqlite://", echo=False)
    await _create_tables(engine)
    SessionLocal = async_sessionmaker(engine, expire_on_commit=False)
    async with SessionLocal() as s:
        yield s
    await engine.dispose()


def test_normalize_github_shorthand():
    from plugin_marketplace import normalize_plugin_source
    n = normalize_plugin_source("acme/plugin-x")
    assert n.kind == "github"
    assert n.url == "acme/plugin-x"


def test_normalize_https_git_url():
    from plugin_marketplace import normalize_plugin_source
    n = normalize_plugin_source("https://gitlab.com/x/y.git")
    assert n.kind == "git"


def test_normalize_relative_path():
    from plugin_marketplace import normalize_plugin_source
    n = normalize_plugin_source("./plugins/x")
    assert n.kind == "relative"
    assert n.path == "./plugins/x"


def test_normalize_object_github():
    from plugin_marketplace import normalize_plugin_source
    n = normalize_plugin_source({"source": "github", "repo": "acme/x", "ref": "v1"})
    assert n.kind == "github"
    assert n.url == "acme/x"
    assert n.ref == "v1"


def test_normalize_object_npm_unsupported():
    from plugin_marketplace import normalize_plugin_source
    n = normalize_plugin_source({"source": "npm", "package": "x"})
    assert n.kind == "unsupported"


def test_manifest_parses_minimal():
    from plugin_marketplace import MarketplaceManifest
    raw = {"name": "test", "plugins": [{"name": "p1", "source": "./p1"}]}
    m = MarketplaceManifest.model_validate(raw)
    assert m.name == "test"
    assert m.plugins[0].name == "p1"


def test_count_ignored_artifacts(tmp_path):
    from plugin_marketplace import _count_ignored_artifacts
    root = tmp_path / "plug"
    (root / "skills" / "s1").mkdir(parents=True)
    (root / "skills" / "s1" / "SKILL.md").write_text("---\nname: s1\n---\nbody")
    (root / "hooks").mkdir()
    (root / "hooks" / "h1.json").write_text("{}")
    (root / "hooks" / "h2.json").write_text("{}")
    (root / "commands").mkdir()
    (root / "commands" / "c1.md").write_text("# c1")
    out = _count_ignored_artifacts(root)
    by_kind = {x["type"]: x["count"] for x in out}
    assert by_kind == {"hooks": 2, "commands": 1}


@pytest.mark.asyncio
async def test_sync_marketplace_local(session, tmp_path):
    from plugin_marketplace import sync_marketplace

    src = tmp_path / "src" / ".claude-plugin"
    src.mkdir(parents=True)
    (src / "marketplace.json").write_text(json.dumps({
        "name": "local-test",
        "plugins": [{"name": "p1", "source": "./p1", "version": "1.0.0"}],
    }))

    mp = Marketplace(
        name="local-test",
        source_type="local",
        source_url=str(tmp_path / "src"),
        enabled=True,
        predefined=False,
    )
    session.add(mp)
    await session.flush()

    await sync_marketplace(mp, session)
    assert mp.last_sync_status == "ok"
    assert mp.last_sync_error is None
    assert mp.cached_manifest["name"] == "local-test"
    assert mp.last_synced_at is not None


@pytest.mark.asyncio
async def test_sync_marketplace_failure_records_error(session, tmp_path):
    from plugin_marketplace import sync_marketplace
    mp = Marketplace(
        name="bad",
        source_type="local",
        source_url=str(tmp_path / "does-not-exist"),
        enabled=True,
        predefined=False,
    )
    session.add(mp)
    await session.flush()
    await sync_marketplace(mp, session)
    assert mp.last_sync_status == "error"
    assert mp.last_sync_error


@pytest.mark.asyncio
async def test_install_plugin_local_marketplace(session, tmp_path):
    from plugin_marketplace import install_plugin, sync_marketplace, plugin_install_dir

    src_root = tmp_path / "src"
    plugin_root = src_root / "p1"
    (plugin_root / ".claude-plugin").mkdir(parents=True)
    (plugin_root / ".claude-plugin" / "plugin.json").write_text(json.dumps({"name": "p1", "version": "1.0.0"}))
    (plugin_root / "skills" / "do-thing").mkdir(parents=True)
    (plugin_root / "skills" / "do-thing" / "SKILL.md").write_text("---\nname: do-thing\ndescription: d\n---\nbody")
    (plugin_root / ".mcp.json").write_text(json.dumps({"slack": {"command": "noop"}}))
    (plugin_root / "hooks").mkdir()
    (plugin_root / "hooks" / "h.json").write_text("{}")

    (src_root / ".claude-plugin").mkdir(parents=True)
    (src_root / ".claude-plugin" / "marketplace.json").write_text(json.dumps({
        "name": "local-mp",
        "plugins": [{"name": "p1", "source": "./p1", "version": "1.0.0"}],
    }))

    mp = Marketplace(name="local-mp", source_type="local", source_url=str(src_root),
                     enabled=True, predefined=False)
    session.add(mp)
    await session.flush()
    await sync_marketplace(mp, session)

    plugin = await install_plugin(
        session=session, marketplace=mp, plugin_name="p1", version="1.0.0",
    )
    assert plugin.installed_version == "1.0.0"
    assert plugin.enabled is False
    assert plugin.ignored_artifacts and plugin.ignored_artifacts[0]["type"] == "hooks"

    install_dir = plugin_install_dir("local-mp", "p1", "1.0.0")
    assert install_dir.is_dir()
    assert (install_dir / ".mcp.json").is_file()


@pytest.mark.asyncio
async def test_uninstall_removes_cache(session, tmp_path):
    from plugin_marketplace import install_plugin, sync_marketplace, uninstall_plugin, plugin_install_dir

    src_root = tmp_path / "src"
    plugin_root = src_root / "p1"
    plugin_root.mkdir(parents=True)
    (plugin_root / "skills" / "x").mkdir(parents=True)
    (plugin_root / "skills" / "x" / "SKILL.md").write_text("---\nname: x\n---\n")
    (src_root / ".claude-plugin").mkdir(parents=True)
    (src_root / ".claude-plugin" / "marketplace.json").write_text(json.dumps({
        "name": "mp", "plugins": [{"name": "p1", "source": "./p1", "version": "0.1.0"}],
    }))

    mp = Marketplace(name="mp", source_type="local", source_url=str(src_root),
                     enabled=True, predefined=False)
    session.add(mp)
    await session.flush()
    await sync_marketplace(mp, session)
    plugin = await install_plugin(session=session, marketplace=mp, plugin_name="p1", version="0.1.0")
    install_dir = plugin_install_dir("mp", "p1", "0.1.0")
    assert install_dir.is_dir()
    await uninstall_plugin(plugin, session)
    assert not install_dir.exists()


@pytest.mark.asyncio
async def test_install_rejects_relative_path_traversal(session, tmp_path):
    """A malicious marketplace.json with a `..` plugin source must be rejected."""
    from plugin_marketplace import install_plugin, sync_marketplace, PluginInstallError

    secret = tmp_path / "secret"
    secret.mkdir()
    (secret / "stolen.txt").write_text("private")

    src_root = tmp_path / "src"
    (src_root / ".claude-plugin").mkdir(parents=True)
    (src_root / ".claude-plugin" / "marketplace.json").write_text(json.dumps({
        "name": "evil-mp",
        "plugins": [{"name": "evil", "source": "../secret", "version": "1.0.0"}],
    }))

    mp = Marketplace(name="evil-mp", source_type="local", source_url=str(src_root),
                     enabled=True, predefined=False)
    session.add(mp)
    await session.flush()
    await sync_marketplace(mp, session)

    with pytest.raises(PluginInstallError, match=r"may not contain"):
        await install_plugin(session=session, marketplace=mp, plugin_name="evil", version="1.0.0")


@pytest.mark.asyncio
async def test_wait_for_plugin_success(session):
    import plugin_marketplace
    pid = uuid.uuid4()
    fut = asyncio.get_event_loop().create_future()
    plugin_marketplace._warm_futures[pid] = fut
    fut.set_result(True)
    assert await plugin_marketplace.wait_for_plugin(pid, timeout=1.0) is True


@pytest.mark.asyncio
async def test_wait_for_plugin_returns_false_on_failure(session):
    import plugin_marketplace
    pid = uuid.uuid4()
    fut = asyncio.get_event_loop().create_future()
    plugin_marketplace._warm_futures[pid] = fut
    fut.set_result(False)
    assert await plugin_marketplace.wait_for_plugin(pid, timeout=1.0) is False


@pytest.mark.asyncio
async def test_wait_for_plugin_no_future_returns_true(session):
    import plugin_marketplace
    # No registered warm — assumed cached, returns True immediately
    assert await plugin_marketplace.wait_for_plugin(uuid.uuid4(), timeout=0.5) is True


@pytest.mark.asyncio
async def test_update_latest_versions_from_manifest(session):
    from plugin_marketplace import update_latest_versions_from_manifest

    mp = Marketplace(name="mp", source_type="github", source_url="x/y",
                     enabled=True, predefined=False,
                     cached_manifest={"name": "mp", "plugins": [
                         {"name": "a", "source": "./a", "version": "2.0.0"},
                         {"name": "b", "source": "./b", "version": "0.5.0"},
                     ]})
    session.add(mp)
    await session.flush()
    p_a = Plugin(marketplace_id=mp.id, plugin_name="a", installed_version="1.0.0",
                 latest_available_version="1.0.0", enabled=False)
    p_b = Plugin(marketplace_id=mp.id, plugin_name="b", installed_version="0.5.0",
                 latest_available_version="0.5.0", enabled=False)
    session.add_all([p_a, p_b])
    await session.flush()

    changed = update_latest_versions_from_manifest(mp, [p_a, p_b])
    assert changed == [p_a]
    assert p_a.latest_available_version == "2.0.0"
    assert p_b.latest_available_version == "0.5.0"


@pytest.mark.asyncio
async def test_sync_marketplace_git_clone_failure_categorized(session, monkeypatch):
    """A git clone failure is captured as a clean, actionable sync error rather
    than the generic 'unexpected error (see server logs)'."""
    import plugin_marketplace as pm

    async def _boom(**kwargs):
        raise RuntimeError("git clone failed: fatal: repository not found")

    monkeypatch.setattr(pm, "fetch_marketplace", _boom)
    mp = Marketplace(
        name="clone-fail",
        source_type="git",
        source_url="https://example.com/x.git",
        enabled=True,
        predefined=False,
    )
    session.add(mp)
    await session.flush()

    await pm.sync_marketplace(mp, session)

    assert mp.last_sync_status == "error"
    assert mp.last_sync_error == "git clone failed (see server logs)"
    assert "unexpected error" not in (mp.last_sync_error or "")


@pytest.mark.asyncio
async def test_sync_marketplace_auth_failure_preserves_status_code(session, monkeypatch):
    """An auth (401) fetch failure records a sanitized last_sync_error that keeps
    the HTTP status code but does not leak the source URL."""
    import plugin_marketplace as pm
    from plugin_marketplace import MarketplaceFetchError

    async def _boom(**kwargs):
        raise MarketplaceFetchError(
            "http fetch failed: Client error '401 Unauthorized' for url "
            "'https://secret.example.com/marketplace.json'"
        )

    monkeypatch.setattr(pm, "fetch_marketplace", _boom)
    mp = Marketplace(
        name="auth-fail",
        source_type="http",
        source_url="https://secret.example.com/marketplace.json",
        enabled=True,
        predefined=False,
    )
    session.add(mp)
    await session.flush()

    await pm.sync_marketplace(mp, session)

    assert mp.last_sync_status == "error"
    assert "401" in mp.last_sync_error
    assert "secret.example.com" not in mp.last_sync_error
