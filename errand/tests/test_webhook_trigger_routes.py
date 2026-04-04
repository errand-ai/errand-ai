"""Tests for webhook trigger CRUD API routes."""

import pytest


@pytest.fixture(autouse=True)
def _ensure_encryption_key(monkeypatch):
    monkeypatch.setenv("CREDENTIAL_ENCRYPTION_KEY", "QqXQtnJMYRkG519FlL64LIGn3R_DvpZfeGgrWcHJV_w=")


@pytest.mark.asyncio
class TestWebhookTriggerCRUD:
    async def test_create_trigger(self, admin_client):
        resp = await admin_client.post("/api/webhook-triggers", json={
            "name": "Jira Bugs",
            "source": "jira",
            "filters": {"event_types": ["issue_created"]},
            "actions": {"add_comment": True},
        })
        assert resp.status_code == 201
        data = resp.json()
        assert data["name"] == "Jira Bugs"
        assert data["source"] == "jira"
        assert data["enabled"] is True
        assert data["has_secret"] is False
        assert "id" in data

    async def test_create_trigger_with_secret(self, admin_client):
        resp = await admin_client.post("/api/webhook-triggers", json={
            "name": "Secret Trigger",
            "source": "jira",
            "webhook_secret": "my-secret-123",
        })
        assert resp.status_code == 201
        data = resp.json()
        assert data["has_secret"] is True

    async def test_list_triggers(self, admin_client):
        await admin_client.post("/api/webhook-triggers", json={"name": "T1", "source": "jira"})
        await admin_client.post("/api/webhook-triggers", json={"name": "T2", "source": "github"})
        resp = await admin_client.get("/api/webhook-triggers")
        assert resp.status_code == 200
        assert len(resp.json()) == 2

    async def test_get_trigger(self, admin_client):
        create = await admin_client.post("/api/webhook-triggers", json={"name": "Get Me", "source": "jira"})
        tid = create.json()["id"]
        resp = await admin_client.get(f"/api/webhook-triggers/{tid}")
        assert resp.status_code == 200
        assert resp.json()["name"] == "Get Me"

    async def test_get_not_found(self, admin_client):
        resp = await admin_client.get("/api/webhook-triggers/00000000-0000-0000-0000-000000000000")
        assert resp.status_code == 404

    async def test_update_trigger(self, admin_client):
        create = await admin_client.post("/api/webhook-triggers", json={"name": "Updatable", "source": "jira"})
        tid = create.json()["id"]
        resp = await admin_client.put(f"/api/webhook-triggers/{tid}", json={"enabled": False})
        assert resp.status_code == 200
        assert resp.json()["enabled"] is False

    async def test_delete_trigger(self, admin_client):
        create = await admin_client.post("/api/webhook-triggers", json={"name": "Deletable", "source": "jira"})
        tid = create.json()["id"]
        resp = await admin_client.delete(f"/api/webhook-triggers/{tid}")
        assert resp.status_code == 204
        # Verify gone
        resp = await admin_client.get(f"/api/webhook-triggers/{tid}")
        assert resp.status_code == 404

    async def test_duplicate_name_rejected(self, admin_client):
        await admin_client.post("/api/webhook-triggers", json={"name": "Unique", "source": "jira"})
        resp = await admin_client.post("/api/webhook-triggers", json={"name": "Unique", "source": "jira"})
        assert resp.status_code == 409

    async def test_non_admin_rejected(self, client):
        resp = await client.post("/api/webhook-triggers", json={"name": "Nope", "source": "jira"})
        assert resp.status_code == 403

    async def test_unknown_filter_key_rejected(self, admin_client):
        resp = await admin_client.post("/api/webhook-triggers", json={
            "name": "Bad Filter",
            "source": "jira",
            "filters": {"priority": ["high"]},
        })
        assert resp.status_code == 422
        assert "priority" in resp.json()["detail"]

    async def test_non_array_filter_rejected(self, admin_client):
        resp = await admin_client.post("/api/webhook-triggers", json={
            "name": "Bad Filter Type",
            "source": "jira",
            "filters": {"event_types": "issue_created"},
        })
        assert resp.status_code == 422

    async def test_unknown_action_key_rejected(self, admin_client):
        resp = await admin_client.post("/api/webhook-triggers", json={
            "name": "Bad Action",
            "source": "jira",
            "actions": {"send_email": True},
        })
        assert resp.status_code == 422
        assert "send_email" in resp.json()["detail"]

    async def test_wrong_action_type_rejected(self, admin_client):
        resp = await admin_client.post("/api/webhook-triggers", json={
            "name": "Bad Action Type",
            "source": "jira",
            "actions": {"add_comment": "yes"},
        })
        assert resp.status_code == 422

    async def test_valid_filters_accepted(self, admin_client):
        resp = await admin_client.post("/api/webhook-triggers", json={
            "name": "Valid Filters",
            "source": "jira",
            "filters": {"event_types": ["issue_created", "issue_updated"], "projects": ["PROJ"]},
        })
        assert resp.status_code == 201

    async def test_valid_actions_accepted(self, admin_client):
        resp = await admin_client.post("/api/webhook-triggers", json={
            "name": "Valid Actions",
            "source": "jira",
            "actions": {"add_comment": True, "transition_on_complete": "Done"},
        })
        assert resp.status_code == 201

    async def test_update_filters_validated(self, admin_client):
        create = await admin_client.post("/api/webhook-triggers", json={"name": "Update Validate", "source": "jira"})
        tid = create.json()["id"]
        resp = await admin_client.put(f"/api/webhook-triggers/{tid}", json={"filters": {"bad_key": ["x"]}})
        assert resp.status_code == 422

    async def test_invalid_uuid_returns_422(self, admin_client):
        resp = await admin_client.get("/api/webhook-triggers/not-a-uuid")
        assert resp.status_code == 422
        assert "Invalid" in resp.json()["detail"]

    async def test_delete_invalid_uuid_returns_422(self, admin_client):
        resp = await admin_client.delete("/api/webhook-triggers/bad-id")
        assert resp.status_code == 422
