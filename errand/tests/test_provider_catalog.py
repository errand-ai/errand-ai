"""The hosted-provider catalog: what it contains and how providers are created from it.

Adding a provider used to mean knowing its base URL. The catalog turns that into
a selection, and carries the one fact a UI cannot derive — whether the provider
lists its models — so that a provider without listing offers typed entry rather
than an empty dropdown.

Every base URL here was verified against the live endpoint at implementation
time. These tests do not re-verify over the network; they guard the shape and
the internal consistency that a careless edit would break.
"""

from unittest.mock import AsyncMock, patch

import pytest
from httpx import AsyncClient

from provider_catalog import (
    OTHER_ENTRY_ID,
    PROVIDER_CATALOG,
    catalog_entry,
    catalog_to_dict,
)


@pytest.fixture(autouse=True)
def set_encryption_key(monkeypatch):
    monkeypatch.setenv("CREDENTIAL_ENCRYPTION_KEY", "_26HOOIDUcxDH7fkoqI39DZulVPVK-hZe5THhiVLxIs=")


class TestCatalogContents:
    def test_ids_are_unique(self):
        ids = [e.id for e in PROVIDER_CATALOG]
        assert len(ids) == len(set(ids))

    def test_recommended_aggregator_is_present(self):
        entry = catalog_entry("openrouter")
        assert entry is not None
        assert entry.base_url == "https://openrouter.ai/api/v1"

    def test_listed_entries_carry_a_base_url_and_a_key_link(self):
        for entry in PROVIDER_CATALOG:
            if entry.requires_base_url:
                continue
            assert entry.base_url, f"{entry.id} has no base URL"
            assert entry.base_url.startswith("https://"), entry.id
            assert entry.api_key_url, f"{entry.id} does not say where to get a key"

    def test_gemini_declares_no_model_listing(self):
        """Its OpenAI-compat surface 404s on /models; chat completions works fine."""
        entry = catalog_entry("google-gemini")
        assert entry is not None
        assert entry.supports_model_listing is False

    def test_most_entries_do_support_listing(self):
        listing = [e for e in PROVIDER_CATALOG if e.supports_model_listing]
        assert len(listing) > 10

    def test_unlisted_entry_exists_and_takes_a_caller_supplied_url(self):
        entry = catalog_entry(OTHER_ENTRY_ID)
        assert entry is not None
        assert entry.requires_base_url is True
        assert entry.base_url is None

    def test_litellm_proxy_is_an_operator_supplied_entry(self):
        """LiteLLM stays available — it is repositioned, not removed."""
        entry = catalog_entry("litellm")
        assert entry is not None
        assert entry.requires_base_url is True

    def test_unknown_id_returns_none(self):
        assert catalog_entry("nope") is None

    def test_serialization_exposes_what_a_ui_needs(self):
        payload = catalog_to_dict(catalog_entry("openrouter"))
        assert payload["id"] == "openrouter"
        assert payload["display_name"]
        assert payload["base_url"] == "https://openrouter.ai/api/v1"
        assert payload["supports_model_listing"] is True
        assert payload["requires_base_url"] is False
        assert payload["api_key_url"]


class TestCatalogEndpoint:
    async def test_catalog_is_offered_for_selection(self, admin_client: AsyncClient):
        resp = await admin_client.get("/api/llm/provider-catalog")

        assert resp.status_code == 200
        entries = resp.json()
        assert len(entries) == len(PROVIDER_CATALOG)
        assert {e["id"] for e in entries} >= {"openrouter", "openai", OTHER_ENTRY_ID}

    async def test_requires_admin(self, client: AsyncClient):
        resp = await client.get("/api/llm/provider-catalog")
        assert resp.status_code == 403


class TestCreateFromCatalog:
    async def test_uses_the_catalog_base_url(self, admin_client: AsyncClient):
        with patch("main.probe_provider_type", new_callable=AsyncMock,
                   return_value="openai_compatible") as probe:
            resp = await admin_client.post("/api/llm/providers", json={
                "catalog_id": "openrouter",
                "api_key": "sk-or-test",
            })

        assert resp.status_code == 201, resp.text
        body = resp.json()
        assert body["base_url"] == "https://openrouter.ai/api/v1"
        assert body["source"] == "database"
        # Probed exactly as a manually entered provider is.
        probe.assert_awaited_once_with("https://openrouter.ai/api/v1", "sk-or-test")

    async def test_defaults_the_name_to_the_display_name(self, admin_client: AsyncClient):
        with patch("main.probe_provider_type", new_callable=AsyncMock, return_value="openai_compatible"):
            resp = await admin_client.post("/api/llm/providers", json={
                "catalog_id": "openrouter", "api_key": "sk-or-test",
            })

        assert resp.json()["name"] == "OpenRouter"

    async def test_a_supplied_name_wins(self, admin_client: AsyncClient):
        with patch("main.probe_provider_type", new_callable=AsyncMock, return_value="openai_compatible"):
            resp = await admin_client.post("/api/llm/providers", json={
                "catalog_id": "openrouter", "api_key": "sk-or-test", "name": "my-router",
            })

        assert resp.json()["name"] == "my-router"

    async def test_unlisted_entry_takes_both_url_and_key(self, admin_client: AsyncClient):
        with patch("main.probe_provider_type", new_callable=AsyncMock, return_value="openai_compatible") as probe:
            resp = await admin_client.post("/api/llm/providers", json={
                "catalog_id": OTHER_ENTRY_ID,
                "base_url": "https://my-gateway.example/v1",
                "api_key": "sk-mine",
                "name": "my-gateway",
            })

        assert resp.status_code == 201, resp.text
        assert resp.json()["base_url"] == "https://my-gateway.example/v1"
        probe.assert_awaited_once_with("https://my-gateway.example/v1", "sk-mine")

    async def test_unlisted_entry_without_a_url_is_rejected(self, admin_client: AsyncClient):
        resp = await admin_client.post("/api/llm/providers", json={
            "catalog_id": OTHER_ENTRY_ID, "api_key": "sk-mine",
        })

        assert resp.status_code == 422
        assert "base_url" in resp.json()["detail"]

    async def test_unknown_catalog_id_is_rejected(self, admin_client: AsyncClient):
        resp = await admin_client.post("/api/llm/providers", json={
            "catalog_id": "not-a-provider", "api_key": "sk-x",
        })

        assert resp.status_code == 422

    async def test_manual_creation_still_works_unchanged(self, admin_client: AsyncClient):
        """No catalog_id — the pre-existing contract."""
        with patch("main.probe_provider_type", new_callable=AsyncMock, return_value="litellm"):
            resp = await admin_client.post("/api/llm/providers", json={
                "name": "hand-rolled",
                "base_url": "https://proxy.example/v1",
                "api_key": "sk-1234",
            })

        assert resp.status_code == 201
        assert resp.json()["name"] == "hand-rolled"

    async def test_manual_creation_without_a_url_is_rejected(self, admin_client: AsyncClient):
        resp = await admin_client.post("/api/llm/providers", json={
            "name": "nameless", "api_key": "sk-1234",
        })

        assert resp.status_code == 422
