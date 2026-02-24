from httpx import AsyncClient

from main import generate_ssh_keypair


# --- GET /api/settings ---


async def test_get_settings_empty(admin_client: AsyncClient):
    resp = await admin_client.get("/api/settings")
    assert resp.status_code == 200
    data = resp.json()
    # New format returns metadata-enriched settings from registry
    assert isinstance(data, dict)
    # Should have registry keys with metadata
    assert "system_prompt" in data
    assert "value" in data["system_prompt"]
    assert "source" in data["system_prompt"]


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
    assert data["system_prompt"]["value"] == "You are a helpful assistant"
    assert data["system_prompt"]["source"] == "database"


async def test_put_settings_update(admin_client: AsyncClient):
    await admin_client.put(
        "/api/settings", json={"system_prompt": "Original prompt"}
    )
    resp = await admin_client.put(
        "/api/settings", json={"system_prompt": "Updated prompt"}
    )
    assert resp.status_code == 200
    assert resp.json()["system_prompt"]["value"] == "Updated prompt"


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
    assert data["system_prompt"]["value"] == "New prompt"
    assert data["mcp_servers"]["value"] == [{"name": "test"}]
    assert data["mcp_servers"]["source"] == "database"


async def test_put_settings_non_admin(client: AsyncClient):
    resp = await client.put(
        "/api/settings", json={"system_prompt": "Nope"}
    )
    assert resp.status_code == 403
    assert resp.json()["detail"] == "Admin role required"


# --- Skills excluded from settings (managed via /api/skills) ---


async def test_get_settings_excludes_skills(admin_client: AsyncClient):
    resp = await admin_client.get("/api/settings")
    assert resp.status_code == 200
    assert "skills" not in resp.json()


async def test_put_settings_ignores_skills(admin_client: AsyncClient):
    resp = await admin_client.put(
        "/api/settings",
        json={"skills": [{"name": "test"}], "system_prompt": "hello"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "skills" not in data
    assert data["system_prompt"]["value"] == "hello"


# --- SSH keypair generation ---


def test_generate_ssh_keypair():
    private_pem, public_openssh = generate_ssh_keypair()
    assert private_pem.startswith("-----BEGIN OPENSSH PRIVATE KEY-----")
    assert public_openssh.startswith("ssh-ed25519 ")
    assert public_openssh.endswith(" errand")


def test_generate_ssh_keypair_unique():
    _, pub1 = generate_ssh_keypair()
    _, pub2 = generate_ssh_keypair()
    assert pub1 != pub2


# --- SSH private key excluded from GET /api/settings ---


async def test_get_settings_excludes_ssh_private_key(admin_client: AsyncClient):
    # Store both keys via PUT
    await admin_client.put(
        "/api/settings",
        json={"ssh_private_key": "PRIVATE", "ssh_public_key": "PUBLIC"},
    )
    resp = await admin_client.get("/api/settings")
    assert resp.status_code == 200
    data = resp.json()
    assert "ssh_public_key" in data
    assert data["ssh_public_key"]["value"] == "PUBLIC"
    assert "ssh_private_key" not in data


# --- POST /api/settings/regenerate-ssh-key ---


async def test_regenerate_ssh_key(admin_client: AsyncClient):
    resp = await admin_client.post("/api/settings/regenerate-ssh-key")
    assert resp.status_code == 200
    data = resp.json()
    assert "ssh_public_key" in data
    assert data["ssh_public_key"].startswith("ssh-ed25519 ")
    # Verify the key is persisted
    resp2 = await admin_client.get("/api/settings")
    assert resp2.json()["ssh_public_key"]["value"] == data["ssh_public_key"]


async def test_regenerate_ssh_key_replaces_existing(admin_client: AsyncClient):
    resp1 = await admin_client.post("/api/settings/regenerate-ssh-key")
    key1 = resp1.json()["ssh_public_key"]
    resp2 = await admin_client.post("/api/settings/regenerate-ssh-key")
    key2 = resp2.json()["ssh_public_key"]
    assert key1 != key2


async def test_regenerate_ssh_key_non_admin(client: AsyncClient):
    resp = await client.post("/api/settings/regenerate-ssh-key")
    assert resp.status_code == 403
    assert resp.json()["detail"] == "Admin role required"
