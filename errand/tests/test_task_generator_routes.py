"""Tests for task generator API routes."""

import pytest


# --- List ---

@pytest.mark.anyio
async def test_list_generators_empty(admin_client):
    resp = await admin_client.get("/api/task-generators")
    assert resp.status_code == 200
    assert resp.json() == []


@pytest.mark.anyio
async def test_list_generators_after_create(admin_client):
    # Create an email generator first
    await admin_client.put("/api/task-generators/email", json={
        "enabled": True,
        "config": {"poll_interval": 120},
    })
    resp = await admin_client.get("/api/task-generators")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    assert data[0]["type"] == "email"


# --- Get email ---

@pytest.mark.anyio
async def test_get_email_generator_not_found(admin_client):
    resp = await admin_client.get("/api/task-generators/email")
    assert resp.status_code == 404


@pytest.mark.anyio
async def test_get_email_generator(admin_client):
    await admin_client.put("/api/task-generators/email", json={
        "enabled": True,
        "profile_id": None,
        "config": {"poll_interval": 90},
    })
    resp = await admin_client.get("/api/task-generators/email")
    assert resp.status_code == 200
    data = resp.json()
    assert data["type"] == "email"
    assert data["enabled"] is True
    assert data["config"]["poll_interval"] == 90


# --- Upsert ---

@pytest.mark.anyio
async def test_create_email_generator(admin_client):
    resp = await admin_client.put("/api/task-generators/email", json={
        "enabled": False,
        "config": {"poll_interval": 60, "task_prompt": "Process this email"},
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["type"] == "email"
    assert data["enabled"] is False
    assert data["config"]["task_prompt"] == "Process this email"


@pytest.mark.anyio
async def test_update_email_generator(admin_client):
    # Create
    await admin_client.put("/api/task-generators/email", json={
        "enabled": False,
        "config": {"poll_interval": 60},
    })

    # Update
    resp = await admin_client.put("/api/task-generators/email", json={
        "enabled": True,
        "config": {"poll_interval": 120, "task_prompt": "Updated prompt"},
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["enabled"] is True
    assert data["config"]["poll_interval"] == 120
    assert data["config"]["task_prompt"] == "Updated prompt"

    # Verify only one record
    list_resp = await admin_client.get("/api/task-generators")
    assert len(list_resp.json()) == 1


@pytest.mark.anyio
async def test_upsert_with_invalid_profile_id(admin_client):
    resp = await admin_client.put("/api/task-generators/email", json={
        "enabled": True,
        "profile_id": "not-a-uuid",
        "config": {},
    })
    assert resp.status_code == 400


# --- Auth ---

@pytest.mark.anyio
async def test_non_admin_rejected(client):
    """Non-admin user should get 403."""
    resp = await client.get("/api/task-generators")
    assert resp.status_code == 403


@pytest.mark.anyio
async def test_poll_interval_validation(admin_client):
    """Poll interval below 60 should be rejected by Pydantic."""
    resp = await admin_client.put("/api/task-generators/email", json={
        "enabled": True,
        "config": {"poll_interval": 10},
    })
    assert resp.status_code == 422
