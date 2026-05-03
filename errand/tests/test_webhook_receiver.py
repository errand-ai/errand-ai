"""Tests for webhook receiver endpoint."""

import hashlib
import hmac
import uuid

import pytest
from unittest.mock import AsyncMock, patch


@pytest.fixture(autouse=True)
def _ensure_encryption_key(monkeypatch):
    monkeypatch.setenv("CREDENTIAL_ENCRYPTION_KEY", "QqXQtnJMYRkG519FlL64LIGn3R_DvpZfeGgrWcHJV_w=")


def _make_signature(secret: str, body: bytes) -> str:
    return "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()


@pytest.fixture(autouse=True)
def clear_dedup_cache():
    """Clear the dedup cache between tests."""
    from webhook_receiver import _dedup_cache
    _dedup_cache.clear()


async def _insert_trigger(session_maker, name, source="jira", secret="test-secret"):
    """Insert a webhook trigger directly via DB with a known plaintext secret.

    The webhook_secret column stores Fernet-encrypted JSON {"secret": "..."}.
    Server-side trigger creation generates a random secret; for receiver tests
    we need a deterministic secret to compute matching signatures.
    """
    import uuid as _uuid
    from models import WebhookTrigger
    from platforms.credentials import encrypt
    async with session_maker() as session:
        trigger = WebhookTrigger(
            id=_uuid.uuid4(),
            name=name,
            source=source,
            webhook_secret=encrypt({"secret": secret}),
        )
        session.add(trigger)
        await session.commit()


@pytest.mark.asyncio
class TestWebhookReceiver:
    async def test_valid_webhook_accepted(self, admin_client_with_session):
        client, session_maker = admin_client_with_session
        await _insert_trigger(session_maker, "Jira Test")
        body = b'{"webhookEvent": "issue_created"}'
        sig = _make_signature("test-secret", body)

        with patch("webhook_receiver._dispatch_webhook", new_callable=AsyncMock) as mock_dispatch:
            resp = await client.post(
                "/webhooks/jira",
                content=body,
                headers={"X-Hub-Signature": sig, "Content-Type": "application/json"},
            )
        assert resp.status_code == 200
        assert resp.json()["status"] == "accepted"
        mock_dispatch.assert_called_once()

    async def test_missing_signature_returns_401(self, admin_client):
        resp = await admin_client.post(
            "/webhooks/jira",
            content=b'{"test": true}',
            headers={"Content-Type": "application/json"},
        )
        assert resp.status_code == 401

    async def test_wrong_signature_returns_401(self, admin_client_with_session):
        client, session_maker = admin_client_with_session
        await _insert_trigger(session_maker, "Wrong Sig Test")
        body = b'{"test": true}'
        resp = await client.post(
            "/webhooks/jira",
            content=body,
            headers={"X-Hub-Signature": "sha256=wrong", "Content-Type": "application/json"},
        )
        assert resp.status_code == 401

    async def test_second_trigger_matches(self, admin_client_with_session):
        client, session_maker = admin_client_with_session
        await _insert_trigger(session_maker, "First", secret="first-secret")
        await _insert_trigger(session_maker, "Second", secret="second-secret")
        body = b'{"test": "match second"}'
        sig = _make_signature("second-secret", body)

        with patch("webhook_receiver._dispatch_webhook", new_callable=AsyncMock) as mock_dispatch:
            resp = await client.post(
                "/webhooks/jira",
                content=body,
                headers={"X-Hub-Signature": sig, "Content-Type": "application/json"},
            )
        assert resp.status_code == 200
        # The dispatched trigger should be the second one
        call_trigger = mock_dispatch.call_args[0][0]
        assert call_trigger.name == "Second"

    async def test_deduplication(self, admin_client_with_session):
        client, session_maker = admin_client_with_session
        await _insert_trigger(session_maker, "Dedup Test")
        body = b'{"test": "dedup"}'
        sig = _make_signature("test-secret", body)
        event_id = str(uuid.uuid4())

        with patch("webhook_receiver._dispatch_webhook", new_callable=AsyncMock):
            # First delivery
            resp1 = await client.post(
                "/webhooks/jira",
                content=body,
                headers={
                    "X-Hub-Signature": sig,
                    "X-Atlassian-Webhook-Identifier": event_id,
                    "Content-Type": "application/json",
                },
            )
            assert resp1.json()["status"] == "accepted"

            # Duplicate delivery
            resp2 = await client.post(
                "/webhooks/jira",
                content=body,
                headers={
                    "X-Hub-Signature": sig,
                    "X-Atlassian-Webhook-Identifier": event_id,
                    "Content-Type": "application/json",
                },
            )
            assert resp2.json()["status"] == "duplicate"

    async def test_empty_body_returns_400(self, admin_client):
        resp = await admin_client.post(
            "/webhooks/jira",
            content=b'',
            headers={"X-Hub-Signature": "sha256=abc", "Content-Type": "application/json"},
        )
        assert resp.status_code == 400

    async def test_no_triggers_returns_401(self, admin_client):
        body = b'{"test": true}'
        sig = _make_signature("any-secret", body)
        resp = await admin_client.post(
            "/webhooks/jira",
            content=body,
            headers={"X-Hub-Signature": sig, "Content-Type": "application/json"},
        )
        assert resp.status_code == 401
