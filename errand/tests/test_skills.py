"""Tests for Skills API endpoints."""
import uuid

from httpx import AsyncClient

from main import validate_skill_name, validate_skill_file_path


# --- Validation helpers ---


def test_validate_skill_name_valid():
    assert validate_skill_name("research") is None
    assert validate_skill_name("code-review") is None
    assert validate_skill_name("a") is None
    assert validate_skill_name("pdf-processing-v2") is None


def test_validate_skill_name_empty():
    assert validate_skill_name("") is not None


def test_validate_skill_name_uppercase():
    assert "lowercase" in validate_skill_name("Research")


def test_validate_skill_name_consecutive_hyphens():
    assert "consecutive" in validate_skill_name("code--review")


def test_validate_skill_name_leading_hyphen():
    assert validate_skill_name("-research") is not None


def test_validate_skill_name_trailing_hyphen():
    assert validate_skill_name("research-") is not None


def test_validate_skill_name_too_long():
    assert "64" in validate_skill_name("a" * 65)


def test_validate_skill_name_special_chars():
    assert validate_skill_name("my_skill") is not None
    assert validate_skill_name("my skill") is not None


def test_validate_file_path_valid():
    assert validate_skill_file_path("scripts/extract.py") is None
    assert validate_skill_file_path("references/REFERENCE.md") is None
    assert validate_skill_file_path("assets/template.json") is None


def test_validate_file_path_wrong_subdir():
    assert validate_skill_file_path("other/file.txt") is not None


def test_validate_file_path_nested_too_deep():
    assert validate_skill_file_path("scripts/lib/utils.py") is not None


def test_validate_file_path_no_subdir():
    assert validate_skill_file_path("file.txt") is not None


def test_validate_file_path_empty():
    assert validate_skill_file_path("") is not None


# --- Helper to create a skill ---

async def _create_skill(client: AsyncClient, name="research", description="Conducts research", instructions="## Steps") -> dict:
    resp = await client.post("/api/skills", json={
        "name": name,
        "description": description,
        "instructions": instructions,
    })
    assert resp.status_code == 201
    return resp.json()


# --- GET /api/skills ---


async def test_list_skills_empty(admin_client: AsyncClient):
    resp = await admin_client.get("/api/skills")
    assert resp.status_code == 200
    assert resp.json() == []


async def test_list_skills_with_data(admin_client: AsyncClient):
    await _create_skill(admin_client, "alpha", "Alpha skill", "Do alpha")
    await _create_skill(admin_client, "beta", "Beta skill", "Do beta")
    resp = await admin_client.get("/api/skills")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 2
    assert data[0]["name"] == "alpha"  # ordered by name
    assert data[1]["name"] == "beta"
    # List should NOT include file content
    assert "content" not in str(data[0].get("files", []))


async def test_list_skills_requires_auth(client: AsyncClient):
    resp = await client.get("/api/skills")
    assert resp.status_code == 200  # authenticated non-admin can list


# --- POST /api/skills ---


async def test_create_skill(admin_client: AsyncClient):
    resp = await admin_client.post("/api/skills", json={
        "name": "research",
        "description": "Conducts web research",
        "instructions": "## Steps\n1. Search the web",
    })
    assert resp.status_code == 201
    data = resp.json()
    assert data["name"] == "research"
    assert data["description"] == "Conducts web research"
    assert data["id"]
    assert data["files"] == []


async def test_create_skill_invalid_name(admin_client: AsyncClient):
    resp = await admin_client.post("/api/skills", json={
        "name": "My Skill",
        "description": "d",
        "instructions": "i",
    })
    assert resp.status_code == 422


async def test_create_skill_duplicate_name(admin_client: AsyncClient):
    await _create_skill(admin_client, "research")
    resp = await admin_client.post("/api/skills", json={
        "name": "research",
        "description": "d",
        "instructions": "i",
    })
    assert resp.status_code == 409


async def test_create_skill_non_admin(client: AsyncClient):
    resp = await client.post("/api/skills", json={
        "name": "research",
        "description": "d",
        "instructions": "i",
    })
    assert resp.status_code == 403


async def test_create_skill_empty_name(admin_client: AsyncClient):
    resp = await admin_client.post("/api/skills", json={
        "name": "",
        "description": "d",
        "instructions": "i",
    })
    assert resp.status_code == 422


async def test_create_skill_description_too_long(admin_client: AsyncClient):
    resp = await admin_client.post("/api/skills", json={
        "name": "test",
        "description": "x" * 1025,
        "instructions": "i",
    })
    assert resp.status_code == 422


# --- GET /api/skills/{id} ---


async def test_get_skill(admin_client: AsyncClient):
    skill = await _create_skill(admin_client)
    resp = await admin_client.get(f"/api/skills/{skill['id']}")
    assert resp.status_code == 200
    data = resp.json()
    assert data["name"] == "research"
    assert data["files"] == []


async def test_get_skill_with_files(admin_client: AsyncClient):
    skill = await _create_skill(admin_client)
    await admin_client.post(f"/api/skills/{skill['id']}/files", json={
        "path": "scripts/extract.py",
        "content": "print('hello')",
    })
    resp = await admin_client.get(f"/api/skills/{skill['id']}")
    data = resp.json()
    assert len(data["files"]) == 1
    assert data["files"][0]["content"] == "print('hello')"  # content included in detail view


async def test_get_skill_not_found(admin_client: AsyncClient):
    resp = await admin_client.get(f"/api/skills/{uuid.uuid4()}")
    assert resp.status_code == 404


# --- PUT /api/skills/{id} ---


async def test_update_skill_instructions(admin_client: AsyncClient):
    skill = await _create_skill(admin_client)
    resp = await admin_client.put(f"/api/skills/{skill['id']}", json={
        "instructions": "## Updated",
    })
    assert resp.status_code == 200
    assert resp.json()["instructions"] == "## Updated"


async def test_update_skill_rename(admin_client: AsyncClient):
    skill = await _create_skill(admin_client)
    resp = await admin_client.put(f"/api/skills/{skill['id']}", json={
        "name": "web-research",
    })
    assert resp.status_code == 200
    assert resp.json()["name"] == "web-research"


async def test_update_skill_rename_duplicate(admin_client: AsyncClient):
    await _create_skill(admin_client, "alpha")
    skill = await _create_skill(admin_client, "beta", "d", "i")
    resp = await admin_client.put(f"/api/skills/{skill['id']}", json={
        "name": "alpha",
    })
    assert resp.status_code == 409


async def test_update_skill_non_admin(client: AsyncClient):
    # Can't update without admin (can't create either, but test the endpoint)
    resp = await client.put(f"/api/skills/{uuid.uuid4()}", json={"name": "test"})
    assert resp.status_code == 403


async def test_update_skill_not_found(admin_client: AsyncClient):
    resp = await admin_client.put(f"/api/skills/{uuid.uuid4()}", json={"name": "test"})
    assert resp.status_code == 404


# --- DELETE /api/skills/{id} ---


async def test_delete_skill(admin_client: AsyncClient):
    skill = await _create_skill(admin_client)
    resp = await admin_client.delete(f"/api/skills/{skill['id']}")
    assert resp.status_code == 204
    # Verify deleted
    resp = await admin_client.get(f"/api/skills/{skill['id']}")
    assert resp.status_code == 404


async def test_delete_skill_with_files(admin_client: AsyncClient):
    skill = await _create_skill(admin_client)
    await admin_client.post(f"/api/skills/{skill['id']}/files", json={
        "path": "scripts/a.py",
        "content": "x",
    })
    await admin_client.post(f"/api/skills/{skill['id']}/files", json={
        "path": "assets/b.json",
        "content": "y",
    })
    resp = await admin_client.delete(f"/api/skills/{skill['id']}")
    assert resp.status_code == 204


async def test_delete_skill_not_found(admin_client: AsyncClient):
    resp = await admin_client.delete(f"/api/skills/{uuid.uuid4()}")
    assert resp.status_code == 404


async def test_delete_skill_non_admin(client: AsyncClient):
    resp = await client.delete(f"/api/skills/{uuid.uuid4()}")
    assert resp.status_code == 403


# --- POST /api/skills/{id}/files ---


async def test_add_file(admin_client: AsyncClient):
    skill = await _create_skill(admin_client)
    resp = await admin_client.post(f"/api/skills/{skill['id']}/files", json={
        "path": "scripts/extract.py",
        "content": "#!/usr/bin/env python3\nprint('hello')",
    })
    assert resp.status_code == 201
    data = resp.json()
    assert data["path"] == "scripts/extract.py"
    assert data["content"] == "#!/usr/bin/env python3\nprint('hello')"


async def test_add_file_invalid_path(admin_client: AsyncClient):
    skill = await _create_skill(admin_client)
    resp = await admin_client.post(f"/api/skills/{skill['id']}/files", json={
        "path": "invalid/file.txt",
        "content": "x",
    })
    assert resp.status_code == 422


async def test_add_file_duplicate_path(admin_client: AsyncClient):
    skill = await _create_skill(admin_client)
    await admin_client.post(f"/api/skills/{skill['id']}/files", json={
        "path": "scripts/extract.py",
        "content": "v1",
    })
    resp = await admin_client.post(f"/api/skills/{skill['id']}/files", json={
        "path": "scripts/extract.py",
        "content": "v2",
    })
    assert resp.status_code == 409


async def test_add_file_skill_not_found(admin_client: AsyncClient):
    resp = await admin_client.post(f"/api/skills/{uuid.uuid4()}/files", json={
        "path": "scripts/a.py",
        "content": "x",
    })
    assert resp.status_code == 404


async def test_add_file_non_admin(client: AsyncClient):
    resp = await client.post(f"/api/skills/{uuid.uuid4()}/files", json={
        "path": "scripts/a.py",
        "content": "x",
    })
    assert resp.status_code == 403


# --- DELETE /api/skills/{id}/files/{file_id} ---


async def test_delete_file(admin_client: AsyncClient):
    skill = await _create_skill(admin_client)
    file_resp = await admin_client.post(f"/api/skills/{skill['id']}/files", json={
        "path": "scripts/extract.py",
        "content": "x",
    })
    file_id = file_resp.json()["id"]
    resp = await admin_client.delete(f"/api/skills/{skill['id']}/files/{file_id}")
    assert resp.status_code == 204


async def test_delete_file_wrong_skill(admin_client: AsyncClient):
    skill1 = await _create_skill(admin_client, "skill-one")
    skill2 = await _create_skill(admin_client, "skill-two", "d", "i")
    file_resp = await admin_client.post(f"/api/skills/{skill1['id']}/files", json={
        "path": "scripts/a.py",
        "content": "x",
    })
    file_id = file_resp.json()["id"]
    # Try to delete from wrong skill
    resp = await admin_client.delete(f"/api/skills/{skill2['id']}/files/{file_id}")
    assert resp.status_code == 404


async def test_delete_file_non_admin(client: AsyncClient):
    resp = await client.delete(f"/api/skills/{uuid.uuid4()}/files/{uuid.uuid4()}")
    assert resp.status_code == 403


# --- Settings API no longer includes skills ---


async def test_get_settings_no_skills(admin_client: AsyncClient):
    """GET /api/settings should not return a skills field."""
    resp = await admin_client.get("/api/settings")
    assert resp.status_code == 200
    assert "skills" not in resp.json()


async def test_put_settings_ignores_skills(admin_client: AsyncClient):
    """PUT /api/settings should ignore a skills field in the body."""
    resp = await admin_client.put("/api/settings", json={
        "skills": [{"name": "ignored"}],
        "system_prompt": "test",
    })
    assert resp.status_code == 200
    data = resp.json()
    assert "skills" not in data
    assert data["system_prompt"]["value"] == "test"
