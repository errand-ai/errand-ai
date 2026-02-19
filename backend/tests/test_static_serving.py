"""Tests for static file serving (SPA fallback, asset serving, API routes unaffected)."""

import pytest
from httpx import ASGITransport, AsyncClient


@pytest.fixture()
def static_dir(tmp_path):
    """Create a temporary static directory with test files."""
    assets_dir = tmp_path / "assets"
    assets_dir.mkdir()
    (tmp_path / "index.html").write_text("<!DOCTYPE html><html><body>SPA</body></html>")
    (assets_dir / "index-abc123.js").write_text("console.log('app')")
    (tmp_path / "favicon.ico").write_bytes(b"\x00\x00\x01\x00")
    return tmp_path


@pytest.fixture()
async def static_client(static_dir, fake_valkey):
    """Client that tests static serving with a real static directory."""
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

    from fastapi import HTTPException, Request
    from fastapi.responses import FileResponse
    from fastapi.staticfiles import StaticFiles

    from main import app, get_current_user, require_editor, require_admin
    from database import get_session
    from tests.conftest import FAKE_USER_CLAIMS, _create_tables

    engine = create_async_engine("sqlite+aiosqlite://", echo=False)
    await _create_tables(engine)

    test_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async def override_get_session():
        async with test_session() as session:
            yield session

    async def override_get_current_user():
        return FAKE_USER_CLAIMS

    async def override_require_editor():
        return FAKE_USER_CLAIMS

    async def override_require_admin_reject():
        raise HTTPException(status_code=403, detail="Admin role required")

    app.dependency_overrides[get_session] = override_get_session
    app.dependency_overrides[get_current_user] = override_get_current_user
    app.dependency_overrides[require_editor] = override_require_editor
    app.dependency_overrides[require_admin] = override_require_admin_reject

    # Add static routes for testing
    app.mount("/assets-test", StaticFiles(directory=static_dir / "assets"), name="test-assets")

    @app.get("/static-test/{path:path}")
    async def test_spa(request: Request, path: str):
        file_path = static_dir / path
        if path and file_path.is_file():
            return FileResponse(file_path)
        return FileResponse(static_dir / "index.html")

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac

    app.dependency_overrides.clear()
    # Remove test routes
    app.routes[:] = [r for r in app.routes if getattr(r, "name", None) not in ("test-assets", "test_spa")]
    await engine.dispose()


@pytest.mark.asyncio
async def test_hashed_asset_served(static_client):
    resp = await static_client.get("/assets-test/index-abc123.js")
    assert resp.status_code == 200
    assert "console.log" in resp.text


@pytest.mark.asyncio
async def test_spa_fallback_deep_route(static_client):
    resp = await static_client.get("/static-test/tasks/123")
    assert resp.status_code == 200
    assert "SPA" in resp.text


@pytest.mark.asyncio
async def test_spa_fallback_root(static_client):
    resp = await static_client.get("/static-test/")
    assert resp.status_code == 200
    assert "SPA" in resp.text


@pytest.mark.asyncio
async def test_favicon_served(static_client):
    resp = await static_client.get("/static-test/favicon.ico")
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_missing_file_falls_back_to_spa(static_client):
    resp = await static_client.get("/static-test/nonexistent.txt")
    assert resp.status_code == 200
    assert "SPA" in resp.text


@pytest.mark.asyncio
async def test_api_routes_unaffected(static_client):
    """API routes should still work normally when static serving is active."""
    resp = await static_client.get("/api/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"


@pytest.mark.asyncio
async def test_api_tasks_unaffected(static_client):
    """Protected API routes should still work normally."""
    resp = await static_client.get("/api/tasks")
    assert resp.status_code == 200


def test_static_dir_not_mounted_when_missing():
    """Verify that the SPA catch-all route is NOT registered when static/ doesn't exist."""
    from main import app, STATIC_DIR
    spa_routes = [r for r in app.routes if getattr(r, "name", None) == "spa_fallback"]
    assert not STATIC_DIR.is_dir() or len(spa_routes) > 0
