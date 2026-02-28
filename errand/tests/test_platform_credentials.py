import pytest
from cryptography.fernet import Fernet

from platforms import get_registry
from platforms.base import Platform, PlatformCapability, PlatformInfo


class FakePlatform(Platform):
    """A fake platform for testing credential CRUD."""

    def __init__(self, *, verify_result: bool = True):
        self._verify_result = verify_result

    def info(self) -> PlatformInfo:
        return PlatformInfo(
            id="fake-platform",
            label="Fake Platform",
            capabilities={PlatformCapability.POST},
            credential_schema=[
                {"name": "api_key", "label": "API Key", "type": "password"},
            ],
        )

    async def verify_credentials(self, credentials: dict) -> bool:
        return self._verify_result


@pytest.fixture(autouse=True)
def _encryption_key(monkeypatch):
    monkeypatch.setenv("CREDENTIAL_ENCRYPTION_KEY", Fernet.generate_key().decode())


@pytest.fixture(autouse=True)
def _register_fake_platform():
    registry = get_registry()
    fake = FakePlatform()
    registry.register(fake)
    yield
    # Clean up: remove the fake platform from the registry
    registry._platforms.pop("fake-platform", None)


# --- List platforms ---


@pytest.mark.anyio
async def test_list_platforms(admin_client):
    resp = await admin_client.get("/api/platforms")
    assert resp.status_code == 200
    data = resp.json()
    ids = [p["id"] for p in data]
    assert "fake-platform" in ids
    fake = next(p for p in data if p["id"] == "fake-platform")
    assert fake["label"] == "Fake Platform"
    assert fake["status"] == "disconnected"
    assert fake["last_verified_at"] is None


@pytest.mark.anyio
async def test_list_platforms_any_authenticated_user(client):
    resp = await client.get("/api/platforms")
    assert resp.status_code == 200
    ids = [p["id"] for p in resp.json()]
    assert "fake-platform" in ids


# --- Save credentials ---


@pytest.mark.anyio
async def test_save_credentials(admin_client):
    resp = await admin_client.put(
        "/api/platforms/fake-platform/credentials",
        json={"api_key": "test-key-123"},
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "connected"

    # Verify the platform now shows as connected
    resp = await admin_client.get("/api/platforms")
    fake = next(p for p in resp.json() if p["id"] == "fake-platform")
    assert fake["status"] == "connected"


@pytest.mark.anyio
async def test_save_credentials_unknown_platform(admin_client):
    resp = await admin_client.put(
        "/api/platforms/nonexistent/credentials",
        json={"api_key": "test"},
    )
    assert resp.status_code == 404


@pytest.mark.anyio
async def test_save_credentials_requires_admin(client):
    resp = await client.put(
        "/api/platforms/fake-platform/credentials",
        json={"api_key": "test"},
    )
    assert resp.status_code == 403


@pytest.mark.anyio
async def test_update_credentials_overwrites(admin_client):
    # Save initial credentials
    await admin_client.put(
        "/api/platforms/fake-platform/credentials",
        json={"api_key": "first-key"},
    )
    # Update with new credentials
    resp = await admin_client.put(
        "/api/platforms/fake-platform/credentials",
        json={"api_key": "second-key"},
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "connected"


# --- Verify credentials ---


@pytest.mark.anyio
async def test_verify_credentials_success(admin_client):
    # Save credentials first
    await admin_client.put(
        "/api/platforms/fake-platform/credentials",
        json={"api_key": "test-key"},
    )

    resp = await admin_client.post("/api/platforms/fake-platform/credentials/verify")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "connected"
    assert data["last_verified_at"] is not None


@pytest.mark.anyio
async def test_verify_credentials_no_creds(admin_client):
    resp = await admin_client.post("/api/platforms/fake-platform/credentials/verify")
    assert resp.status_code == 400
    assert "No credentials configured" in resp.json()["detail"]


@pytest.mark.anyio
async def test_verify_credentials_failure(admin_client):
    # Register a platform that fails verification
    registry = get_registry()
    # Override info to use a different ID
    class FailingPlatform(FakePlatform):
        def info(self):
            info = super().info()
            return PlatformInfo(
                id="failing-platform",
                label="Failing Platform",
                capabilities=info.capabilities,
                credential_schema=info.credential_schema,
            )
    failing_platform = FailingPlatform(verify_result=False)
    registry.register(failing_platform)

    try:
        # Save should fail because verification fails
        save_resp = await admin_client.put(
            "/api/platforms/failing-platform/credentials",
            json={"api_key": "bad-key"},
        )
        assert save_resp.status_code == 400
        assert "verification failed" in save_resp.json()["detail"].lower()
    finally:
        registry._platforms.pop("failing-platform", None)


@pytest.mark.anyio
async def test_verify_credentials_requires_admin(client):
    resp = await client.post("/api/platforms/fake-platform/credentials/verify")
    assert resp.status_code == 403


# --- Delete credentials ---


@pytest.mark.anyio
async def test_delete_credentials(admin_client):
    # Save credentials first
    await admin_client.put(
        "/api/platforms/fake-platform/credentials",
        json={"api_key": "test-key"},
    )

    resp = await admin_client.delete("/api/platforms/fake-platform/credentials")
    assert resp.status_code == 204

    # Verify the platform now shows as disconnected
    resp = await admin_client.get("/api/platforms")
    fake = next(p for p in resp.json() if p["id"] == "fake-platform")
    assert fake["status"] == "disconnected"


@pytest.mark.anyio
async def test_delete_credentials_idempotent(admin_client):
    resp = await admin_client.delete("/api/platforms/fake-platform/credentials")
    assert resp.status_code == 204


@pytest.mark.anyio
async def test_delete_credentials_requires_admin(client):
    resp = await client.delete("/api/platforms/fake-platform/credentials")
    assert resp.status_code == 403


# --- Fake platform with editable fields ---


class EditableFakePlatform(Platform):
    """A fake platform with editable and non-editable fields."""

    def __init__(self, *, verify_result: bool = True):
        self._verify_result = verify_result

    def info(self) -> PlatformInfo:
        return PlatformInfo(
            id="editable-fake",
            label="Editable Fake",
            capabilities={PlatformCapability.POST},
            credential_schema=[
                {"key": "api_key", "label": "API Key", "type": "password"},
                {"key": "profile", "label": "Profile", "type": "text", "editable": True},
                {"key": "interval", "label": "Interval", "type": "text", "editable": True},
            ],
        )

    async def verify_credentials(self, credentials: dict) -> bool:
        return self._verify_result


@pytest.fixture(autouse=True)
def _register_editable_fake():
    registry = get_registry()
    platform = EditableFakePlatform()
    registry.register(platform)
    yield
    registry._platforms.pop("editable-fake", None)


# --- PATCH credentials ---


@pytest.mark.anyio
async def test_patch_editable_field(admin_client):
    # Save initial credentials
    await admin_client.put(
        "/api/platforms/editable-fake/credentials",
        json={"api_key": "secret", "profile": "old", "interval": "60"},
    )

    resp = await admin_client.patch(
        "/api/platforms/editable-fake/credentials",
        json={"profile": "new-profile"},
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "connected"

    # Verify the value was updated
    get_resp = await admin_client.get("/api/platforms/editable-fake/credentials")
    assert get_resp.json()["field_values"]["profile"] == "new-profile"
    # Other editable field unchanged
    assert get_resp.json()["field_values"]["interval"] == "60"


@pytest.mark.anyio
async def test_patch_reject_non_editable_field(admin_client):
    await admin_client.put(
        "/api/platforms/editable-fake/credentials",
        json={"api_key": "secret", "profile": "old", "interval": "60"},
    )

    resp = await admin_client.patch(
        "/api/platforms/editable-fake/credentials",
        json={"api_key": "hacked"},
    )
    assert resp.status_code == 400
    assert "Non-editable" in resp.json()["detail"]


@pytest.mark.anyio
async def test_patch_no_credentials(admin_client):
    resp = await admin_client.patch(
        "/api/platforms/editable-fake/credentials",
        json={"profile": "new"},
    )
    assert resp.status_code == 400
    assert "No credentials configured" in resp.json()["detail"]


@pytest.mark.anyio
async def test_patch_unknown_platform(admin_client):
    resp = await admin_client.patch(
        "/api/platforms/nonexistent/credentials",
        json={"profile": "new"},
    )
    assert resp.status_code == 404


@pytest.mark.anyio
async def test_patch_requires_admin(client):
    resp = await client.patch(
        "/api/platforms/editable-fake/credentials",
        json={"profile": "new"},
    )
    assert resp.status_code == 403


# --- GET credentials with field_values ---


@pytest.mark.anyio
async def test_get_credentials_field_values(admin_client):
    await admin_client.put(
        "/api/platforms/editable-fake/credentials",
        json={"api_key": "secret", "profile": "my-profile", "interval": "120"},
    )

    resp = await admin_client.get("/api/platforms/editable-fake/credentials")
    assert resp.status_code == 200
    data = resp.json()
    assert data["field_values"] == {"profile": "my-profile", "interval": "120"}
    # api_key is NOT editable, so should not appear in field_values
    assert "api_key" not in data["field_values"]


@pytest.mark.anyio
async def test_get_credentials_no_creds_empty_field_values(admin_client):
    resp = await admin_client.get("/api/platforms/editable-fake/credentials")
    assert resp.status_code == 200
    assert resp.json()["field_values"] == {}


@pytest.mark.anyio
async def test_get_credentials_no_editable_fields(admin_client):
    """Platform with no editable fields returns empty field_values."""
    await admin_client.put(
        "/api/platforms/fake-platform/credentials",
        json={"api_key": "secret"},
    )

    resp = await admin_client.get("/api/platforms/fake-platform/credentials")
    assert resp.status_code == 200
    assert resp.json()["field_values"] == {}
