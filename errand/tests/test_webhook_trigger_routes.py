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
        # Server auto-generates webhook_secret on insert
        assert data["has_secret"] is True
        # Cloud not connected in tests, so cloud_webhook_url remains null
        assert data["cloud_webhook_url"] is None
        assert "id" in data

    async def test_webhook_secret_not_user_settable(self, admin_client):
        # webhook_secret in request body is ignored; server auto-generates
        resp = await admin_client.post("/api/webhook-triggers", json={
            "name": "Secret Trigger",
            "source": "jira",
            "webhook_secret": "should-be-ignored",
        })
        assert resp.status_code == 201
        data = resp.json()
        assert data["has_secret"] is True

    async def test_list_triggers(self, admin_client):
        await admin_client.post("/api/webhook-triggers", json={"name": "T1", "source": "jira"})
        await admin_client.post("/api/webhook-triggers", json={
            "name": "T2", "source": "github",
            "filters": {"project_node_id": "PVT_abc", "trigger_column": "Todo"},
        })
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

    async def test_update_preserves_existing_webhook_secret(self, admin_client_with_session):
        """5.4 — update preserves the existing webhook_secret (not regenerated)."""
        import uuid as _uuid
        from sqlalchemy import select
        from models import WebhookTrigger

        client, session_maker = admin_client_with_session

        create = await client.post("/api/webhook-triggers", json={"name": "Preserve Me", "source": "jira"})
        tid = create.json()["id"]
        tid_uuid = _uuid.UUID(tid)

        async with session_maker() as session:
            trigger = (await session.execute(
                select(WebhookTrigger).where(WebhookTrigger.id == tid_uuid)
            )).scalar_one()
            original_secret = trigger.webhook_secret
            assert original_secret  # server-generated on insert

        resp = await client.put(f"/api/webhook-triggers/{tid}", json={"name": "Renamed"})
        assert resp.status_code == 200

        async with session_maker() as session:
            trigger = (await session.execute(
                select(WebhookTrigger).where(WebhookTrigger.id == tid_uuid)
            )).scalar_one()
            assert trigger.webhook_secret == original_secret


class TestCloudRegistrationOnTriggerCreate:
    """5.1 / 5.7 — trigger create with cloud connected calls helper with correct trigger."""

    @pytest.mark.asyncio
    @pytest.mark.parametrize("source", ["jira", "github"])
    async def test_create_invokes_cloud_registration(self, admin_client, source, monkeypatch):
        from unittest.mock import AsyncMock
        import cloud_endpoints

        called: list = []

        async def stub(trigger, session):
            called.append((str(trigger.id), trigger.source, trigger.name))

        monkeypatch.setattr(cloud_endpoints, "register_webhook_trigger_with_cloud", stub)

        body = {"name": f"T-{source}", "source": source}
        if source == "github":
            body["filters"] = {"project_node_id": "PVT_x", "trigger_column": "Todo"}

        resp = await admin_client.post("/api/webhook-triggers", json=body)
        assert resp.status_code == 201
        assert len(called) == 1
        assert called[0][1] == source
        assert called[0][2] == f"T-{source}"

    @pytest.mark.asyncio
    async def test_enabled_toggle_does_not_reregister(self, admin_client, monkeypatch):
        """Toggling `enabled` should not round-trip cloud — name/source/filters/actions
        are the only fields that affect the cloud endpoint or its label."""
        import cloud_endpoints

        registrations: list = []

        async def reg_stub(trigger, session):
            registrations.append(str(trigger.id))

        monkeypatch.setattr(cloud_endpoints, "register_webhook_trigger_with_cloud", reg_stub)

        create = await admin_client.post("/api/webhook-triggers", json={"name": "ToggleMe", "source": "jira"})
        tid = create.json()["id"]
        # 1 call from create
        assert len(registrations) == 1

        resp = await admin_client.put(f"/api/webhook-triggers/{tid}", json={"enabled": False})
        assert resp.status_code == 200
        # No additional call from enabled-only update
        assert len(registrations) == 1

        # Updating name DOES re-register
        resp = await admin_client.put(f"/api/webhook-triggers/{tid}", json={"name": "Renamed"})
        assert resp.status_code == 200
        assert len(registrations) == 2

    @pytest.mark.asyncio
    async def test_delete_invokes_cloud_revocation(self, admin_client, monkeypatch):
        from unittest.mock import AsyncMock
        import cloud_endpoints

        revoked: list = []

        async def stub(trigger, session):
            revoked.append((str(trigger.id), trigger.source))

        monkeypatch.setattr(cloud_endpoints, "revoke_webhook_trigger_in_cloud", stub)
        # Also stub the registration call so it doesn't error
        async def reg_stub(trigger, session):
            return None
        monkeypatch.setattr(cloud_endpoints, "register_webhook_trigger_with_cloud", reg_stub)

        create = await admin_client.post("/api/webhook-triggers", json={"name": "DelMe", "source": "jira"})
        tid = create.json()["id"]
        resp = await admin_client.delete(f"/api/webhook-triggers/{tid}")
        assert resp.status_code == 204
        assert len(revoked) == 1
        assert revoked[0][0] == tid
