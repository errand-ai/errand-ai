"""Tests for GET /api/version endpoint."""
from unittest.mock import patch

import pytest


@pytest.mark.asyncio
async def test_version_endpoint_returns_expected_shape(client):
    with patch("main.get_version_info", return_value={
        "current": "0.65.0",
        "latest": "0.66.0",
        "update_available": True,
    }):
        resp = await client.get("/api/version")

    assert resp.status_code == 200
    data = resp.json()
    assert data["current"] == "0.65.0"
    assert data["latest"] == "0.66.0"
    assert data["update_available"] is True


@pytest.mark.asyncio
async def test_version_endpoint_no_auth_required(unauth_client):
    with patch("main.get_version_info", return_value={
        "current": "dev",
        "latest": None,
        "update_available": False,
    }):
        resp = await unauth_client.get("/api/version")

    assert resp.status_code == 200
    data = resp.json()
    assert data["current"] == "dev"
    assert data["latest"] is None
    assert data["update_available"] is False
