from httpx import AsyncClient


# --- GET /api/settings ---


async def test_get_settings_empty(admin_client: AsyncClient):
    resp = await admin_client.get("/api/settings")
    assert resp.status_code == 200
    data = resp.json()
    # skills defaults to empty array even when no settings exist
    assert data == {"skills": []}


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


# --- Skills in settings ---


async def test_get_settings_skills_default_empty(admin_client: AsyncClient):
    resp = await admin_client.get("/api/settings")
    assert resp.status_code == 200
    assert resp.json()["skills"] == []


async def test_put_settings_skills_roundtrip(admin_client: AsyncClient):
    skills = [
        {
            "id": "abc-123",
            "name": "researcher",
            "description": "Web research skill",
            "instructions": "You are a research specialist.",
        }
    ]
    resp = await admin_client.put("/api/settings", json={"skills": skills})
    assert resp.status_code == 200
    assert resp.json()["skills"] == skills

    # Verify GET returns the same data
    resp = await admin_client.get("/api/settings")
    assert resp.json()["skills"] == skills


async def test_put_settings_skills_update(admin_client: AsyncClient):
    skills_v1 = [{"id": "1", "name": "a", "description": "d1", "instructions": "i1"}]
    await admin_client.put("/api/settings", json={"skills": skills_v1})

    skills_v2 = [
        {"id": "1", "name": "a", "description": "d1", "instructions": "i1-updated"},
        {"id": "2", "name": "b", "description": "d2", "instructions": "i2"},
    ]
    resp = await admin_client.put("/api/settings", json={"skills": skills_v2})
    assert resp.status_code == 200
    assert resp.json()["skills"] == skills_v2
