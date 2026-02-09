from httpx import AsyncClient


# --- GET /api/settings ---


async def test_get_settings_empty(admin_client: AsyncClient):
    resp = await admin_client.get("/api/settings")
    assert resp.status_code == 200
    assert resp.json() == {}


async def test_get_settings_non_admin(client: AsyncClient):
    resp = await client.get("/api/settings")
    assert resp.status_code == 403
    assert resp.json()["detail"] == "Admin role required"


# --- PUT /api/settings ---


async def test_put_settings_create(admin_client: AsyncClient):
    resp = await admin_client.put(
        "/api/settings", json={"system_prompt": "You are a helpful assistant"}
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["system_prompt"] == "You are a helpful assistant"


async def test_put_settings_update(admin_client: AsyncClient):
    await admin_client.put(
        "/api/settings", json={"system_prompt": "Original prompt"}
    )
    resp = await admin_client.put(
        "/api/settings", json={"system_prompt": "Updated prompt"}
    )
    assert resp.status_code == 200
    assert resp.json()["system_prompt"] == "Updated prompt"


async def test_put_settings_partial_preserves_other_keys(admin_client: AsyncClient):
    await admin_client.put(
        "/api/settings",
        json={"system_prompt": "My prompt", "mcp_servers": [{"name": "test"}]},
    )
    resp = await admin_client.put(
        "/api/settings", json={"system_prompt": "New prompt"}
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["system_prompt"] == "New prompt"
    assert data["mcp_servers"] == [{"name": "test"}]


async def test_put_settings_non_admin(client: AsyncClient):
    resp = await client.put(
        "/api/settings", json={"system_prompt": "Nope"}
    )
    assert resp.status_code == 403
    assert resp.json()["detail"] == "Admin role required"
