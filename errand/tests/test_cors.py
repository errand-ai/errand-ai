"""CORS policy tests.

Hardening rather than a live fix: errand is Bearer-only and sets no cookies,
so the wildcard this replaces was not exploitable. It becomes exploitable the
moment cookie auth is introduced, which is the latent hazard being removed.
"""

import os
from unittest.mock import patch

from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from main import app, configure_cors, cors_origins


def test_default_configuration_is_not_a_wildcard():
    with patch.dict(os.environ, {}, clear=True):
        assert "*" not in cors_origins()


def test_default_configuration_is_empty():
    """Every supported deployment is same-origin, which needs no CORS at all."""
    with patch.dict(os.environ, {}, clear=True):
        assert cors_origins() == []


def test_configured_origins_are_parsed():
    with patch.dict(os.environ, {"CORS_ALLOWED_ORIGINS": "https://a.example, https://b.example"}):
        assert cors_origins() == ["https://a.example", "https://b.example"]


def test_explicit_wildcard_is_stripped():
    """A deployment cannot reintroduce the wildcard through configuration."""
    with patch.dict(os.environ, {"CORS_ALLOWED_ORIGINS": "*,https://a.example"}):
        assert cors_origins() == ["https://a.example"]


def _app_with_origins(value: str) -> FastAPI:
    target = FastAPI()

    @target.get("/probe")
    async def probe():
        return {"ok": True}

    with patch.dict(os.environ, {"CORS_ALLOWED_ORIGINS": value}):
        configure_cors(target)
    return target


async def _probe(target: FastAPI, origin: str):
    transport = ASGITransport(app=target)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        return await ac.get("/probe", headers={"Origin": origin})


async def test_configured_origin_is_granted_access():
    resp = await _probe(_app_with_origins("https://ui.example"), "https://ui.example")
    assert resp.headers.get("access-control-allow-origin") == "https://ui.example"


async def test_unconfigured_origin_is_not_granted_access():
    resp = await _probe(_app_with_origins("https://ui.example"), "https://evil.example")
    assert "access-control-allow-origin" not in resp.headers


async def test_running_app_does_not_grant_arbitrary_origins():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        resp = await ac.get("/health", headers={"Origin": "https://evil.example"})
    assert resp.headers.get("access-control-allow-origin") != "*"
    assert "access-control-allow-origin" not in resp.headers


async def test_credentials_are_not_allowed():
    """Unset `allow_credentials` is what keeps a loose origin list harmless."""
    resp = await _probe(_app_with_origins("https://ui.example"), "https://ui.example")
    assert "access-control-allow-credentials" not in resp.headers


async def test_same_origin_request_succeeds_with_no_configuration():
    """The standard deployment: the server serves its own frontend.

    A same-origin browser request carries no `Origin` header, so CORS never
    applies — this asserts the empty default does not get in its way.
    """
    target = _app_with_origins("")
    transport = ASGITransport(app=target)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        resp = await ac.get("/probe")

    assert resp.status_code == 200
    assert resp.json() == {"ok": True}
