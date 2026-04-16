"""Tests for static file serving (SPA fallback, asset serving, API routes unaffected).

The fixture below mirrors the production wiring in ``errand/main.py``:
auth/API routes are registered first, then ``/assets`` is mounted as a vanilla
``StaticFiles`` (so missing assets return 404), then the production
``SPAStaticFiles`` class is mounted at ``/`` so deep links fall back to
``index.html``. Exercising the real class (rather than re-implementing it in the
fixture) means the test suite catches behavioural drift if the production class
is changed.
"""

import pytest
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from httpx import ASGITransport, AsyncClient


@pytest.fixture()
def static_dir(tmp_path):
    """Create a temporary static directory with the files the tests expect."""
    assets_dir = tmp_path / "assets"
    assets_dir.mkdir()
    (tmp_path / "index.html").write_text(
        "<!DOCTYPE html><html><body>SPA</body></html>"
    )
    (assets_dir / "index-abc123.js").write_text("console.log('app')")
    (tmp_path / "favicon.ico").write_bytes(b"\x00\x00\x01\x00")
    (tmp_path / "robots.txt").write_text("User-agent: *\nDisallow:\n")
    return tmp_path


@pytest.fixture()
async def static_client(static_dir):
    """Async client backed by a fresh FastAPI app wired like production.

    Order matches ``errand/main.py``:
      1. Stub auth + API routes registered first (must not be swallowed by SPA).
      2. ``/assets`` mounted as vanilla ``StaticFiles`` (404 on miss).
      3. ``SPAStaticFiles`` mounted at ``/`` with ``html=True``.
    """
    from main import SPAStaticFiles

    test_app = FastAPI()

    # 1. Auth/API routes (registered BEFORE the SPA mount so they match first).
    @test_app.get("/auth/login")
    async def auth_login_stub():
        return JSONResponse({"route": "auth_login"})

    @test_app.get("/api/health")
    async def api_health_stub():
        return JSONResponse({"status": "ok"})

    # 2. /assets mount: vanilla StaticFiles (missing files return 404).
    # Matches production wiring in errand/main.py.
    test_app.mount(
        "/assets",
        StaticFiles(directory=static_dir / "assets"),
        name="static-assets",
    )

    # 3. SPA mount at root: SPAStaticFiles falls back to index.html on 404.
    test_app.mount(
        "/",
        SPAStaticFiles(directory=static_dir, html=True),
        name="spa",
    )

    transport = ASGITransport(app=test_app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest.mark.asyncio
async def test_hashed_asset_served(static_client):
    resp = await static_client.get("/assets/index-abc123.js")
    assert resp.status_code == 200
    assert "console.log" in resp.text


@pytest.mark.asyncio
async def test_spa_fallback_deep_route(static_client):
    resp = await static_client.get("/tasks/123")
    assert resp.status_code == 200
    assert "SPA" in resp.text
    assert resp.headers["content-type"].startswith("text/html")


@pytest.mark.asyncio
async def test_spa_fallback_root(static_client):
    resp = await static_client.get("/")
    assert resp.status_code == 200
    assert "SPA" in resp.text
    assert resp.headers["content-type"].startswith("text/html")


@pytest.mark.asyncio
async def test_favicon_served(static_client):
    resp = await static_client.get("/favicon.ico")
    assert resp.status_code == 200
    assert resp.content == b"\x00\x00\x01\x00"
    assert resp.headers["content-type"].startswith("image/")


@pytest.mark.asyncio
async def test_robots_txt_served(static_client):
    """Scenario 3.11: GET /robots.txt returns text/plain."""
    resp = await static_client.get("/robots.txt")
    assert resp.status_code == 200
    assert "User-agent" in resp.text
    assert resp.headers["content-type"].startswith("text/plain")


@pytest.mark.asyncio
async def test_missing_file_falls_back_to_spa(static_client):
    resp = await static_client.get("/nonexistent.txt")
    assert resp.status_code == 200
    assert "SPA" in resp.text


@pytest.mark.asyncio
async def test_spa_fallback_via_head(static_client):
    """Scenario 3.4: HEAD /tasks/123 returns 200 with text/html."""
    resp = await static_client.head("/tasks/123")
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/html")
    # HEAD responses must not include a body.
    assert resp.content == b""


@pytest.mark.asyncio
async def test_spa_fallback_trailing_slash(static_client):
    """Scenario 3.5: GET /tasks/abc/ (trailing slash) returns SPA HTML."""
    resp = await static_client.get("/tasks/abc/")
    assert resp.status_code == 200
    assert "SPA" in resp.text


@pytest.mark.asyncio
async def test_missing_asset_returns_404(static_client):
    """Scenario 3.6: missing /assets/* returns 404, NOT the SPA fallback."""
    resp = await static_client.get("/assets/missing.js")
    assert resp.status_code == 404
    assert "SPA" not in resp.text


@pytest.mark.asyncio
async def test_deep_link_with_html_extension_falls_back(static_client):
    """Scenario 3.7: deep link with .html extension still falls back to SPA."""
    resp = await static_client.get("/deep/link/missing.html")
    assert resp.status_code == 200
    assert "SPA" in resp.text


@pytest.mark.asyncio
async def test_url_encoded_traversal_does_not_leak(static_client):
    """Scenario 3.8: %2e%2e traversal does not leak files outside static/."""
    resp = await static_client.get("/%2e%2e/%2e%2e/etc/passwd")
    # Must not contain /etc/passwd contents (root: usually appears in passwd).
    assert "root:" not in resp.text
    assert "/bin/bash" not in resp.text
    # Either falls back to SPA HTML (200) or is rejected (4xx); never 200 with passwd.
    if resp.status_code == 200:
        assert "SPA" in resp.text


@pytest.mark.asyncio
async def test_double_slash_does_not_leak(static_client):
    """Scenario 3.9: //etc/passwd does not leak system files."""
    resp = await static_client.get("//etc/passwd")
    assert "root:" not in resp.text
    assert "/bin/bash" not in resp.text
    if resp.status_code == 200:
        assert "SPA" in resp.text


@pytest.mark.asyncio
async def test_path_traversal_blocked(static_client):
    """Literal traversal attempts must not serve files outside the static dir.

    HTTP clients and ASGI normalize ``../`` out of URLs before routing, so the
    request never reaches the SPA handler — Starlette's StaticFiles also
    rejects traversal internally. Either way, /etc/passwd contents must not
    appear in the response.
    """
    resp = await static_client.get("/../../../etc/passwd")
    assert "root:" not in resp.text
    assert "/bin/bash" not in resp.text


@pytest.mark.asyncio
async def test_hidden_file_falls_back_to_spa(static_client):
    """Scenario 3.12: /.env and /.git/config fall back to SPA HTML."""
    for path in ("/.env", "/.git/config"):
        resp = await static_client.get(path)
        assert resp.status_code == 200, f"unexpected status for {path}: {resp.status_code}"
        assert "SPA" in resp.text, f"expected SPA fallback for {path}, got: {resp.text!r}"


@pytest.mark.asyncio
async def test_auth_route_not_swallowed(static_client):
    """Scenario 3.13: /auth/login resolves to the auth route, not the SPA mount.

    The fixture registers the stub /auth/login route BEFORE mounting
    SPAStaticFiles, so the SPA mount must not capture this path.
    """
    resp = await static_client.get("/auth/login")
    assert resp.status_code == 200
    assert resp.json() == {"route": "auth_login"}


@pytest.mark.asyncio
async def test_api_route_not_swallowed(static_client):
    """Spec scenario "API routes unaffected": /api/* resolves to the API route,
    not the SPA mount.

    The fixture registers the stub /api/health route BEFORE mounting
    SPAStaticFiles, so the SPA mount must not capture this path. Guards the
    route-ordering invariant for any future fixture/wiring change.
    """
    resp = await static_client.get("/api/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}
    assert resp.headers["content-type"].startswith("application/json")


@pytest.mark.asyncio
async def test_missing_assets_dir_still_returns_404(tmp_path):
    """Partial-build guard: static/ exists but static/assets/ does NOT at first.

    Reproduces the edge case where the frontend build output is incomplete
    (index.html present, assets/ missing). Production code creates the empty
    assets/ directory at startup so the /assets mount always registers; the
    mount then returns hard 404s for missing files instead of letting the
    request fall through to the SPA mount and silently serve index.html.
    """
    from main import SPAStaticFiles

    # Intentionally do NOT create assets/ — just index.html. Mirror the
    # production startup logic that ensures the directory exists.
    (tmp_path / "index.html").write_text("<!DOCTYPE html><html><body>SPA</body></html>")
    assets_dir = tmp_path / "assets"
    assets_dir.mkdir(exist_ok=True)

    test_app = FastAPI()
    test_app.mount(
        "/assets",
        StaticFiles(directory=assets_dir),
        name="static-assets",
    )
    test_app.mount("/", SPAStaticFiles(directory=tmp_path, html=True), name="spa")

    transport = ASGITransport(app=test_app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        resp = await ac.get("/assets/anything.js")

    assert resp.status_code == 404, (
        f"expected 404 when assets/ dir is empty, got {resp.status_code}; "
        f"body: {resp.text[:200]!r}"
    )
    assert "SPA" not in resp.text, "must not fall back to SPA HTML for /assets/*"


def test_static_dir_not_mounted_when_missing():
    """Verify that the SPA mount is NOT registered when static/ doesn't exist.

    In dev/CI the ``errand/static`` directory is absent (no Vue build), so the
    production app should NOT have a mount named ``"spa"``. In environments
    where the directory exists (e.g. inside the production container), the
    mount must be present.
    """
    from main import app, STATIC_DIR

    spa_mounts = [r for r in app.routes if getattr(r, "name", None) == "spa"]
    if STATIC_DIR.is_dir():
        assert len(spa_mounts) == 1, (
            "expected a single mount named 'spa' when STATIC_DIR exists"
        )
    else:
        assert spa_mounts == [], (
            "expected no 'spa' mount when STATIC_DIR is missing"
        )
