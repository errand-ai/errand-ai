"""Tests for internal credentials endpoint."""
import pytest
from cryptography.fernet import Fernet

from platforms import get_registry
from platforms.base import Platform, PlatformCapability, PlatformInfo


class _InternalTestPlatform(Platform):
    def info(self) -> PlatformInfo:
        return PlatformInfo(
            id="internal-test-platform",
            label="Internal Test",
            capabilities={PlatformCapability.POST},
            credential_schema=[
                {"key": "api_key", "label": "API Key", "type": "password", "required": True},
            ],
        )

    async def verify_credentials(self, credentials: dict) -> bool:
        return True


@pytest.fixture(autouse=True)
def _encryption_key(monkeypatch):
    monkeypatch.setenv("CREDENTIAL_ENCRYPTION_KEY", Fernet.generate_key().decode())


@pytest.fixture(autouse=True)
def _register_test_platform():
    registry = get_registry()
    platform = _InternalTestPlatform()
    registry.register(platform)
    yield
    registry._platforms.pop("internal-test-platform", None)


@pytest.mark.anyio
async def test_get_internal_credentials_success(admin_client):
    """Test retrieving credentials when they exist."""
    # Store credentials via the admin API
    resp = await admin_client.put(
        "/api/platforms/internal-test-platform/credentials",
        json={"api_key": "test-key-123"},
    )
    assert resp.status_code == 200

    # Retrieve via internal endpoint (no auth required)
    resp = await admin_client.get("/api/internal/credentials/internal-test-platform")
    assert resp.status_code == 200
    data = resp.json()
    assert data == {"api_key": "test-key-123"}


@pytest.mark.anyio
async def test_get_internal_credentials_not_configured(client):
    """Test response when no credentials are configured."""
    resp = await client.get("/api/internal/credentials/internal-test-platform")
    assert resp.status_code == 404
    assert resp.json()["detail"] == "No credentials configured"


@pytest.mark.anyio
async def test_get_internal_credentials_unknown_platform(client):
    """Test response when platform doesn't exist in registry."""
    resp = await client.get("/api/internal/credentials/nonexistent-platform")
    assert resp.status_code == 404
    assert "not found" in resp.json()["detail"].lower()
