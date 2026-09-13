"""Establishing the model settings a first run needs, without guessing one.

A newly installed errand has a provider and no model, and nothing in the
product ever asks which to use. These cover the half of that errand can answer
by itself — a provider with exactly one model — and, more importantly, the
larger half it must not: a listing carries no mode, and chat, embedding,
reranker and speech models arrive in one undifferentiated list.
"""

import uuid
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from llm_providers import encrypt_api_key
from models import LlmProvider, Setting

# Measured from a real oMLX server. Chat, embedding, reranker and speech, in
# the order the runtime returns them, with no field distinguishing them.
REAL_MIXED_LISTING = [
    "Qwen3.8-27B-MLX-4bit",
    "Qwen3.8-27B-MLX-8bit",
    "GLM-4.7-Flash-MLX-8bit",
    "Qwen3-Embedding-0.6B-4bit-DWQ",
    "Qwen3-Reranker-4B-mxfp8",
    "whisper-large-v3-turbo",
]


@pytest.fixture(autouse=True)
def set_encryption_key(monkeypatch):
    monkeypatch.setenv("CREDENTIAL_ENCRYPTION_KEY", "_26HOOIDUcxDH7fkoqI39DZulVPVK-hZe5THhiVLxIs=")


@pytest.fixture
async def session_maker():
    engine = create_async_engine("sqlite+aiosqlite://", echo=False)
    async with engine.begin() as conn:
        from tests.conftest import _LLM_PROVIDERS_TABLE_SQL, _SETTINGS_TABLE_SQL
        await conn.execute(text(_LLM_PROVIDERS_TABLE_SQL))
        await conn.execute(text(_SETTINGS_TABLE_SQL))
    maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    yield maker
    await engine.dispose()


async def _provider(session_maker, name="ollama") -> LlmProvider:
    provider = LlmProvider(
        id=uuid.uuid4(), name=name, base_url=f"http://host.docker.internal:11434/v1",
        api_key_encrypted=encrypt_api_key("sk-no-key-required"),
        provider_type="openai_compatible", is_default=True, source="detected",
    )
    async with session_maker() as session:
        session.add(provider)
        await session.commit()
    return provider


def _listing(models):
    """Patch the provider model listing with what a runtime would return."""
    return patch("llm_providers.list_provider_model_ids", AsyncMock(return_value=models))


async def _settings(session_maker) -> dict:
    async with session_maker() as session:
        rows = (await session.execute(select(Setting))).scalars().all()
        return {r.key: r.value for r in rows}


class TestEstablishingFromASoleModel:
    async def test_a_provider_with_one_model_establishes_it(self, session_maker):
        from llm_providers import establish_model_settings_if_unset

        provider = await _provider(session_maker)
        with _listing(["qwen3:8b"]):
            async with session_maker() as session:
                established = await establish_model_settings_if_unset(session, provider)

        assert established == "qwen3:8b"
        settings = await _settings(session_maker)
        assert settings["llm_model"] == {"provider_id": str(provider.id), "model": "qwen3:8b"}
        assert settings["task_processing_model"] == {"provider_id": str(provider.id), "model": "qwen3:8b"}

    async def test_both_roles_are_set_not_one(self, session_maker):
        """Setting one leaves this change's own defect alive in the other: the
        task either still parks for want of a title model, or still fails at the
        runner."""
        from llm_providers import establish_model_settings_if_unset

        provider = await _provider(session_maker)
        with _listing(["qwen3:8b"]):
            async with session_maker() as session:
                await establish_model_settings_if_unset(session, provider)

        settings = await _settings(session_maker)
        assert {"llm_model", "task_processing_model"} <= set(settings)


class TestNeverGuessing:
    async def test_several_models_establish_nothing(self, session_maker):
        from llm_providers import establish_model_settings_if_unset

        provider = await _provider(session_maker)
        with _listing(REAL_MIXED_LISTING):
            async with session_maker() as session:
                established = await establish_model_settings_if_unset(session, provider)

        assert established is None
        assert await _settings(session_maker) == {}

    async def test_the_first_listed_model_is_not_taken(self, session_maker):
        """Ordering is not evidence. Another runtime's first entry is whisper."""
        from llm_providers import establish_model_settings_if_unset

        provider = await _provider(session_maker)
        with _listing(["whisper-large-v3-turbo"] + REAL_MIXED_LISTING[:3]):
            async with session_maker() as session:
                await establish_model_settings_if_unset(session, provider)

        assert await _settings(session_maker) == {}

    async def test_names_are_not_used_to_narrow_the_list(self, session_maker):
        """Excluding by name is rejected in this capability already: a substring
        check for `embed` misses `bge-m3`."""
        from llm_providers import establish_model_settings_if_unset

        provider = await _provider(session_maker)
        # Exactly one entry looks like a chat model by name; a heuristic would
        # seize on it. There is still nothing here that establishes it is one.
        with _listing(["gemma-4-26b-it", "bge-m3", "Qwen3-Reranker-4B"]):
            async with session_maker() as session:
                await establish_model_settings_if_unset(session, provider)

        assert await _settings(session_maker) == {}

    async def test_an_unreadable_listing_establishes_nothing(self, session_maker):
        from llm_providers import establish_model_settings_if_unset

        provider = await _provider(session_maker)
        with _listing(None):
            async with session_maker() as session:
                established = await establish_model_settings_if_unset(session, provider)

        assert established is None
        assert await _settings(session_maker) == {}

    async def test_an_empty_listing_establishes_nothing(self, session_maker):
        from llm_providers import establish_model_settings_if_unset

        provider = await _provider(session_maker)
        with _listing([]):
            async with session_maker() as session:
                assert await establish_model_settings_if_unset(session, provider) is None


class TestExistingSettingsAreKept:
    async def test_a_configured_installation_is_not_touched(self, session_maker):
        """The empty-installation rule detection already uses for the default
        provider: with nothing configured there is nothing to override."""
        from llm_providers import establish_model_settings_if_unset

        provider = await _provider(session_maker)
        async with session_maker() as session:
            session.add(Setting(key="llm_model",
                                value={"provider_id": str(provider.id), "model": "chosen-by-hand"}))
            session.add(Setting(key="task_processing_model",
                                value={"provider_id": str(provider.id), "model": "chosen-by-hand"}))
            await session.commit()

        with _listing(["qwen3:8b"]):
            async with session_maker() as session:
                established = await establish_model_settings_if_unset(session, provider)

        assert established is None
        settings = await _settings(session_maker)
        assert settings["llm_model"]["model"] == "chosen-by-hand"
        assert settings["task_processing_model"]["model"] == "chosen-by-hand"

    async def test_a_partially_configured_installation_is_not_touched(self, session_maker):
        """One role set is not "none configured". Overwriting it would discard a
        deliberate choice on the strength of a scan the user did not connect to
        their model settings."""
        from llm_providers import establish_model_settings_if_unset

        provider = await _provider(session_maker)
        async with session_maker() as session:
            session.add(Setting(key="task_processing_model",
                                value={"provider_id": str(provider.id), "model": "chosen-by-hand"}))
            await session.commit()

        with _listing(["qwen3:8b"]):
            async with session_maker() as session:
                established = await establish_model_settings_if_unset(session, provider)

        assert established is None
        assert (await _settings(session_maker))["task_processing_model"]["model"] == "chosen-by-hand"


# --- The API: stating a choice, and asking whether one has been made --------


def _api_listing(models):
    return patch("main.list_provider_model_ids", AsyncMock(return_value=models))


async def _make_provider(admin_client, name="ollama", url="http://host.docker.internal:11434/v1"):
    with patch("main.probe_provider_type", new_callable=AsyncMock, return_value="openai_compatible"):
        resp = await admin_client.post("/api/llm/providers", json={
            "name": name, "base_url": url, "api_key": "sk-x",
        })
    return resp.json()


class TestStatingAChoice:
    async def test_a_listed_model_is_established(self, admin_client):
        provider = await _make_provider(admin_client)

        with _api_listing(["qwen3:8b", "gemma-4-26b"]):
            resp = await admin_client.post("/api/llm/model-selection", json={
                "provider_id": provider["id"], "model": "qwen3:8b",
            })

        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["model_configured"] is True
        assert body["model"] == "qwen3:8b"
        assert body["provider_id"] == provider["id"]

    async def test_it_governs_both_roles(self, admin_client):
        """Leaving either unset keeps the defect alive in that role."""
        provider = await _make_provider(admin_client)
        with _api_listing(["qwen3:8b"]):
            await admin_client.post("/api/llm/model-selection", json={
                "provider_id": provider["id"], "model": "qwen3:8b",
            })

        settings = (await admin_client.get("/api/settings")).json()
        for key in ("llm_model", "task_processing_model"):
            assert settings[key]["value"]["model"] == "qwen3:8b", f"{key} was not set"
            assert settings[key]["value"]["provider_id"] == provider["id"]

    async def test_the_caller_does_not_name_the_settings(self, admin_client):
        """One operation, not a settings write: a caller carrying the current
        role keys would silently configure a subset when a role is added."""
        provider = await _make_provider(admin_client)
        with _api_listing(["qwen3:8b"]):
            resp = await admin_client.post("/api/llm/model-selection", json={
                "provider_id": provider["id"], "model": "qwen3:8b",
            })

        assert resp.status_code == 200
        assert "llm_model" not in resp.request.content.decode()
        assert "task_processing_model" not in resp.request.content.decode()

    async def test_a_model_the_provider_does_not_serve_is_refused(self, admin_client):
        provider = await _make_provider(admin_client)

        with _api_listing(["qwen3:8b"]):
            resp = await admin_client.post("/api/llm/model-selection", json={
                "provider_id": provider["id"], "model": "a-model-it-does-not-have",
            })

        assert resp.status_code == 422, resp.text
        settings = (await admin_client.get("/api/settings")).json()
        assert settings["llm_model"]["value"]["model"] == ""

    async def test_a_provider_that_does_not_exist_is_refused(self, admin_client):
        resp = await admin_client.post("/api/llm/model-selection", json={
            "provider_id": str(uuid.uuid4()), "model": "qwen3:8b",
        })

        assert resp.status_code == 404, resp.text

    async def test_an_unreadable_listing_refuses_rather_than_trusting_the_caller(self, admin_client):
        provider = await _make_provider(admin_client)

        with _api_listing(None):
            resp = await admin_client.post("/api/llm/model-selection", json={
                "provider_id": provider["id"], "model": "qwen3:8b",
            })

        assert resp.status_code in (422, 502), resp.text

    async def test_requires_admin(self, client):
        resp = await client.post("/api/llm/model-selection", json={
            "provider_id": str(uuid.uuid4()), "model": "m",
        })
        assert resp.status_code == 403


class TestAskingWhetherAModelIsConfigured:
    async def test_an_unconfigured_installation_says_so(self, admin_client):
        resp = await admin_client.get("/api/llm/model-selection")

        assert resp.status_code == 200
        assert resp.json()["model_configured"] is False

    async def test_it_is_readable_without_running_a_scan(self, admin_client):
        """A card renders on mount. A scan is a side-effecting reconciliation,
        not a question."""
        with patch("local_ai_detection.scan_local_ai", new_callable=AsyncMock) as scan:
            resp = await admin_client.get("/api/llm/model-selection")

        assert resp.status_code == 200
        scan.assert_not_called()

    async def test_a_configured_installation_says_so(self, admin_client):
        provider = await _make_provider(admin_client)
        with _api_listing(["qwen3:8b"]):
            await admin_client.post("/api/llm/model-selection", json={
                "provider_id": provider["id"], "model": "qwen3:8b",
            })

        body = (await admin_client.get("/api/llm/model-selection")).json()
        assert body["model_configured"] is True
        assert body["model"] == "qwen3:8b"

    async def test_a_setting_naming_a_departed_provider_is_not_configured(self, admin_client):
        """It looks configured and cannot be used — the direction that hurts,
        because a caller would report all is well while every task fails."""
        provider = await _make_provider(admin_client)
        second = await _make_provider(admin_client, name="other", url="https://other.example/v1")
        with _api_listing(["qwen3:8b"]):
            await admin_client.post("/api/llm/model-selection", json={
                "provider_id": provider["id"], "model": "qwen3:8b",
            })
        await admin_client.put(f"/api/llm/providers/{second['id']}/default")
        await admin_client.delete(f"/api/llm/providers/{provider['id']}")

        body = (await admin_client.get("/api/llm/model-selection")).json()
        assert body["model_configured"] is False


class TestTheCardsSettingShapeIsUnderstood:
    """`resolve_model_setting` accepts `model_id` as well as `model` — the shared
    LlmModelCard writes it. Reading only `model` would report such an
    installation as unconfigured, and then a sole-model scan would overwrite a
    selection the user had already made.
    """

    async def test_a_model_id_only_setting_counts_as_configured(self, session_maker):
        from llm_providers import model_selection_state

        provider = await _provider(session_maker)
        async with session_maker() as session:
            for key in ("llm_model", "task_processing_model"):
                session.add(Setting(key=key, value={"provider_id": str(provider.id),
                                                    "model_id": "saved-by-the-card"}))
            await session.commit()

        async with session_maker() as session:
            state = await model_selection_state(session)

        assert state["model_configured"] is True
        assert state["model"] == "saved-by-the-card"

    async def test_a_model_id_only_setting_is_not_overwritten_by_a_scan(self, session_maker):
        from llm_providers import establish_model_settings_if_unset

        provider = await _provider(session_maker)
        async with session_maker() as session:
            session.add(Setting(key="llm_model", value={"provider_id": str(provider.id),
                                                        "model_id": "saved-by-the-card"}))
            await session.commit()

        with _listing(["qwen3:8b"]):
            async with session_maker() as session:
                assert await establish_model_settings_if_unset(session, provider) is None


class TestEitherNameForTheModel:
    """`model` is canonical; `model_id` is what the shared LlmModelCard writes.

    `resolve_model_setting` has accepted either for a long time, and the
    selection operation accepting only one would leave a client sending
    `model_id` to the settings and `model` here — two names for one concept
    from a single card, with a translation layer in between. Translation layers
    are where the next mismatch hides; this repository has just paid for that
    twice.
    """

    async def test_the_canonical_name_is_accepted(self, admin_client):
        provider = await _make_provider(admin_client)
        with _api_listing(["qwen3:8b"]):
            resp = await admin_client.post("/api/llm/model-selection", json={
                "provider_id": provider["id"], "model": "qwen3:8b",
            })
        assert resp.status_code == 200, resp.text
        assert resp.json()["model"] == "qwen3:8b"

    async def test_the_cards_name_is_accepted(self, admin_client):
        provider = await _make_provider(admin_client)
        with _api_listing(["qwen3:8b"]):
            resp = await admin_client.post("/api/llm/model-selection", json={
                "provider_id": provider["id"], "model_id": "qwen3:8b",
            })
        assert resp.status_code == 200, resp.text
        assert resp.json()["model"] == "qwen3:8b"

    async def test_neither_name_is_rejected(self, admin_client):
        provider = await _make_provider(admin_client)
        resp = await admin_client.post("/api/llm/model-selection", json={
            "provider_id": provider["id"],
        })
        assert resp.status_code == 422

    async def test_an_empty_model_is_rejected(self, admin_client):
        provider = await _make_provider(admin_client)
        resp = await admin_client.post("/api/llm/model-selection", json={
            "provider_id": provider["id"], "model": "",
        })
        assert resp.status_code == 422

    async def test_every_surface_that_reads_a_model_accepts_either_name(self):
        """The invariant, not the instance.

        The `model`/`model_id` defect survived because tolerance was decided
        per call site: `resolve_model_setting` accepted both, so nobody noticed
        `model_selection_state` did not. Asserting it once, over the sites,
        means the next site cannot quietly forget.
        """
        import inspect

        import llm_providers

        for fn in (llm_providers.resolve_model_setting,
                   llm_providers.model_selection_state):
            src = inspect.getsource(fn)
            assert '"model_id"' in src or "'model_id'" in src, (
                f"{fn.__name__} reads a model setting without accepting the "
                f"`model_id` the shared card writes"
            )

    async def test_the_response_carries_only_the_contract(self, admin_client):
        """`any_role_configured` gates whether a scan may establish settings. It
        is a detail of this server's rule, not part of what a caller asked, and
        emitting it invites a consumer to branch on it."""
        resp = await admin_client.get("/api/llm/model-selection")

        assert set(resp.json()) == {"model_configured", "provider_id", "model"}

    async def test_the_post_returns_the_same_shape(self, admin_client):
        provider = await _make_provider(admin_client)
        with _api_listing(["qwen3:8b"]):
            resp = await admin_client.post("/api/llm/model-selection", json={
                "provider_id": provider["id"], "model": "qwen3:8b",
            })

        assert set(resp.json()) == {"model_configured", "provider_id", "model"}


class TestEstablishingDoesNotOverwriteALateChoice:
    async def test_a_choice_made_while_the_listing_is_in_flight_survives(self, session_maker):
        """The empty check precedes a network call, so the window between them
        is as long as the listing takes. A user who chooses during it must not
        have their choice replaced by the sole-model result that arrives after.
        """
        from llm_providers import establish_model_settings_if_unset

        provider = await _provider(session_maker)

        async def listing_that_races(_provider):
            # The user picks while /models is in flight.
            async with session_maker() as session:
                for key in ("llm_model", "task_processing_model"):
                    session.add(Setting(key=key, value={"provider_id": str(provider.id),
                                                        "model": "chosen-by-the-user"}))
                await session.commit()
            return ["the-sole-model"]

        with patch("llm_providers.list_provider_model_ids", side_effect=listing_that_races):
            async with session_maker() as session:
                established = await establish_model_settings_if_unset(session, provider)

        assert established is None, "the late arrival overwrote a live choice"
        assert (await _settings(session_maker))["llm_model"]["model"] == "chosen-by-the-user"
