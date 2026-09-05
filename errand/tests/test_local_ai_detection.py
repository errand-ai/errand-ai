"""Local AI detection — probing the host gateway for OpenAI-compatible runtimes.

The scan contacts a fixed enumeration of well-known endpoints, never a port
range, and registers what answers as a provider with source="detected". It
mirrors `scan_env_providers` in shape, including the reconciliation that
removes rows for runtimes that have gone away.
"""

import os
import uuid
from unittest.mock import patch

import pytest
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from llm_providers import encrypt_api_key
from local_ai_detection import (
    DETECTED_API_KEY,
    LOCAL_AI_CANDIDATES,
    candidate_ports,
    identify_runtime,
    scan_local_ai,
)
from models import LlmProvider, Setting


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


def _ollama_models() -> dict:
    return {"object": "list", "data": [{"id": "qwen3:8b", "owned_by": "library"}]}


def _anonymous_models() -> dict:
    """A response with no marker identifying which runtime produced it."""
    return {"object": "list", "data": [{"id": "some-model"}]}


def _responders(responding: dict[int, dict]):
    """Build probe/fetch fakes where only the given ports answer."""

    async def fake_probe(base_url, api_key):
        port = int(base_url.split(":")[2].split("/")[0])
        return "openai_compatible" if port in responding else "unknown"

    async def fake_fetch(base_url):
        port = int(base_url.split(":")[2].split("/")[0])
        return responding.get(port)

    return fake_probe, fake_fetch


async def _scan(session_maker, responding: dict[int, dict], env: dict | None = None):
    probe, fetch = _responders(responding)
    environ = {
        "HOST_GATEWAY_ADDRESS": "host.docker.internal",
        # clear=True wipes the key the autouse fixture set, and encryption
        # is not what these tests are about.
        "CREDENTIAL_ENCRYPTION_KEY": os.environ["CREDENTIAL_ENCRYPTION_KEY"],
    }
    environ.update(env or {})
    with patch("local_ai_detection.probe_provider_type", side_effect=probe) as probe_mock, \
            patch("local_ai_detection._fetch_models", side_effect=fetch), \
            patch.dict("os.environ", environ, clear=True):
        async with session_maker() as session:
            result = await scan_local_ai(session)
    return result, probe_mock


async def _providers(session_maker) -> list[LlmProvider]:
    async with session_maker() as session:
        rows = await session.execute(select(LlmProvider).order_by(LlmProvider.name))
        return list(rows.scalars().all())


# --- The candidate table ---------------------------------------------------


class TestCandidateTable:
    def test_covers_the_documented_runtimes(self):
        by_name = {c.name: c.port for c in LOCAL_AI_CANDIDATES}
        assert by_name["ollama"] == 11434
        assert by_name["lm-studio"] == 1234
        assert by_name["jan"] == 1337
        assert by_name["vllm"] == 8000
        assert by_name["gpt4all"] == 4891
        assert by_name["mlx"] == 10240

    def test_shared_default_port_is_represented_once_per_runtime(self):
        """llama.cpp and LocalAI both default to 8080 — both are candidates."""
        on_8080 = sorted(c.name for c in LOCAL_AI_CANDIDATES if c.port == 8080)
        assert on_8080 == ["llama.cpp", "localai"]

    def test_ports_are_probed_once_each(self):
        ports = candidate_ports()
        assert len(ports) == len(set(ports))
        assert 8080 in ports


# --- Identification --------------------------------------------------------


class TestIdentifyRuntime:
    def test_identified_from_the_response(self):
        assert identify_runtime(_ollama_models(), port=11434) == "ollama"

    def test_response_wins_over_the_port(self):
        """A runtime answering on someone else's default port is still named correctly."""
        assert identify_runtime(_ollama_models(), port=8080) == "ollama"

    def test_unidentified_on_an_unambiguous_port_uses_that_candidate(self):
        assert identify_runtime(_anonymous_models(), port=11434) == "ollama"

    def test_unidentified_on_a_shared_port_claims_no_runtime(self):
        """8080 could be llama.cpp or LocalAI; guessing either would be a lie."""
        name = identify_runtime(_anonymous_models(), port=8080)
        assert name not in ("llama.cpp", "localai")
        assert "8080" in name

    def test_unknown_port_is_named_by_endpoint(self):
        assert "9999" in identify_runtime(_anonymous_models(), port=9999)


# --- Scanning --------------------------------------------------------------


class TestScan:
    async def test_responding_runtime_is_registered(self, session_maker):
        result, _ = await _scan(session_maker, {11434: _ollama_models()})

        assert result["available"] is True
        providers = await _providers(session_maker)
        assert len(providers) == 1
        assert providers[0].name == "ollama"
        assert providers[0].source == "detected"
        assert providers[0].provider_type == "openai_compatible"

    async def test_stored_url_is_the_url_that_answered(self, session_maker):
        """Not localhost — the gateway address, which is what consumers resolve."""
        await _scan(session_maker, {11434: _ollama_models()})

        providers = await _providers(session_maker)
        assert providers[0].base_url == "http://host.docker.internal:11434/v1"

    async def test_uses_the_configured_gateway_address(self, session_maker):
        await _scan(
            session_maker, {11434: _ollama_models()},
            env={"HOST_GATEWAY_ADDRESS": "192.168.64.1"},
        )

        providers = await _providers(session_maker)
        assert providers[0].base_url == "http://192.168.64.1:11434/v1"

    async def test_api_key_sentinel_is_stored(self, session_maker):
        """Local runtimes ignore Authorization, but the column is NOT NULL."""
        from llm_providers import decrypt_api_key

        await _scan(session_maker, {11434: _ollama_models()})

        providers = await _providers(session_maker)
        assert decrypt_api_key(providers[0].api_key_encrypted) == DETECTED_API_KEY

    async def test_only_fixed_candidates_are_contacted(self, session_maker):
        _, probe_mock = await _scan(session_maker, {})

        probed_ports = sorted(
            int(call.args[0].split(":")[2].split("/")[0]) for call in probe_mock.call_args_list
        )
        assert probed_ports == sorted(candidate_ports())

    async def test_nothing_running_reports_rather_than_fails(self, session_maker):
        result, _ = await _scan(session_maker, {})

        assert result["available"] is True
        assert result["detected"] == []
        assert await _providers(session_maker) == []

    async def test_shared_port_disambiguated_by_response(self, session_maker):
        """A llama.cpp response on 8080 must not be registered as LocalAI, or vice versa."""
        llamacpp = {"object": "list", "data": [{"id": "m", "owned_by": "llamacpp"}]}
        result, _ = await _scan(session_maker, {8080: llamacpp})

        providers = await _providers(session_maker)
        assert [p.name for p in providers] == ["llama.cpp"]
        assert result["detected"][0]["name"] == "llama.cpp"


class TestReconciliation:
    async def test_rescan_updates_rather_than_duplicates(self, session_maker):
        await _scan(session_maker, {11434: _ollama_models()})
        await _scan(session_maker, {11434: _ollama_models()})

        providers = await _providers(session_maker)
        assert len(providers) == 1

    async def test_departed_runtime_is_removed(self, session_maker):
        await _scan(session_maker, {11434: _ollama_models()})
        assert len(await _providers(session_maker)) == 1

        await _scan(session_maker, {})

        assert await _providers(session_maker) == []

    async def test_manually_configured_provider_is_untouched(self, session_maker):
        async with session_maker() as session:
            session.add(LlmProvider(
                id=uuid.uuid4(),
                name="my-proxy",
                base_url="https://proxy.example/v1",
                api_key_encrypted=encrypt_api_key("sk-real"),
                provider_type="litellm",
                is_default=True,
                source="database",
            ))
            await session.commit()

        await _scan(session_maker, {})

        providers = await _providers(session_maker)
        assert [p.name for p in providers] == ["my-proxy"]
        assert providers[0].base_url == "https://proxy.example/v1"
        assert providers[0].is_default is True

    async def test_a_name_held_by_another_source_is_not_taken_over(self, session_maker):
        """An operator's own provider called "ollama" is theirs, not the scan's."""
        async with session_maker() as session:
            session.add(LlmProvider(
                id=uuid.uuid4(),
                name="ollama",
                base_url="https://remote-ollama.example/v1",
                api_key_encrypted=encrypt_api_key("sk-real"),
                provider_type="openai_compatible",
                is_default=True,
                source="database",
            ))
            await session.commit()

        await _scan(session_maker, {11434: _ollama_models()})

        by_name = {p.name: p for p in await _providers(session_maker)}
        # Theirs is untouched...
        assert by_name["ollama"].source == "database"
        assert by_name["ollama"].base_url == "https://remote-ollama.example/v1"
        assert by_name["ollama"].is_default is True
        # ...and the real local runtime is still detected, under a name that
        # does not collide. Refusing to register it would mean a user whose own
        # provider happens to be called "ollama" can never detect their Ollama.
        assert by_name["ollama-11434"].source == "detected"
        assert by_name["ollama-11434"].base_url == "http://host.docker.internal:11434/v1"
        assert by_name["ollama-11434"].is_default is False

    async def test_a_renamed_detected_provider_survives_a_rescan(self, session_maker):
        """The endpoint is the identity; the name is the user's to change.

        Reconciling by name meant a renamed provider matched nothing on the next
        scan, so it was deleted as departed — clearing any model settings that
        pointed at it — and re-created as a duplicate under the original name.
        """
        await _scan(session_maker, {11434: _ollama_models()})
        original = (await _providers(session_maker))[0]

        async with session_maker() as session:
            row = await session.get(LlmProvider, original.id)
            row.name = "my-local-box"
            await session.commit()

        await _scan(session_maker, {11434: _ollama_models()})

        providers = await _providers(session_maker)
        assert len(providers) == 1, "the renamed provider was duplicated or replaced"
        assert providers[0].id == original.id
        assert providers[0].name == "my-local-box", "the scan overwrote the user's name"
        assert providers[0].source == "detected"

    async def test_a_renamed_provider_keeps_its_model_settings(self, session_maker):
        await _scan(session_maker, {11434: _ollama_models()})
        provider_id = (await _providers(session_maker))[0].id

        async with session_maker() as session:
            row = await session.get(LlmProvider, provider_id)
            row.name = "my-local-box"
            session.add(Setting(
                key="task_processing_model",
                value={"provider_id": str(provider_id), "model": "qwen3:8b"},
            ))
            await session.commit()

        await _scan(session_maker, {11434: _ollama_models()})

        async with session_maker() as session:
            setting = (await session.execute(
                select(Setting).where(Setting.key == "task_processing_model")
            )).scalar_one()
            assert setting.value["provider_id"] == str(provider_id)

    async def test_two_endpoints_identifying_as_the_same_runtime(self, session_maker):
        """Keying by endpoint makes this possible; keying by name hid it."""
        vllm = {"object": "list", "data": [{"id": "m", "owned_by": "vllm"}]}
        await _scan(session_maker, {8000: vllm, 8080: vllm})

        providers = await _providers(session_maker)
        assert len(providers) == 2
        assert {p.base_url for p in providers} == {
            "http://host.docker.internal:8000/v1",
            "http://host.docker.internal:8080/v1",
        }
        assert len({p.name for p in providers}) == 2, "names must not collide"

    async def test_departed_runtime_clears_model_settings_pointing_at_it(self, session_maker):
        await _scan(session_maker, {11434: _ollama_models()})
        provider_id = (await _providers(session_maker))[0].id

        async with session_maker() as session:
            session.add(Setting(
                key="task_processing_model",
                value={"provider_id": str(provider_id), "model": "qwen3:8b"},
            ))
            await session.commit()

        await _scan(session_maker, {})

        async with session_maker() as session:
            setting = (await session.execute(
                select(Setting).where(Setting.key == "task_processing_model")
            )).scalar_one()
            assert setting.value == {"provider_id": None, "model": ""}


class TestDefaultSelection:
    async def test_first_provider_on_an_empty_install_becomes_default(self, session_maker):
        await _scan(session_maker, {11434: _ollama_models()})

        providers = await _providers(session_maker)
        assert providers[0].is_default is True

    async def test_existing_default_is_preserved(self, session_maker):
        async with session_maker() as session:
            session.add(LlmProvider(
                id=uuid.uuid4(),
                name="my-proxy",
                base_url="https://proxy.example/v1",
                api_key_encrypted=encrypt_api_key("sk-real"),
                provider_type="litellm",
                is_default=True,
                source="database",
            ))
            await session.commit()

        await _scan(session_maker, {11434: _ollama_models()})

        providers = {p.name: p for p in await _providers(session_maker)}
        assert providers["my-proxy"].is_default is True
        assert providers["ollama"].is_default is False

    async def test_only_one_detected_provider_becomes_default(self, session_maker):
        """Two runtimes found on an empty install must not both claim the default."""
        llamacpp = {"object": "list", "data": [{"id": "m", "owned_by": "llamacpp"}]}
        await _scan(session_maker, {11434: _ollama_models(), 8080: llamacpp})

        providers = await _providers(session_maker)
        assert len(providers) == 2
        assert sum(1 for p in providers if p.is_default) == 1


class TestUnavailable:
    async def test_kubernetes_reports_unavailable_and_probes_nothing(self, session_maker):
        result, probe_mock = await _scan(
            session_maker, {11434: _ollama_models()},
            env={"CONTAINER_RUNTIME": "kubernetes"},
        )

        assert result["available"] is False
        assert result["detected"] == []
        probe_mock.assert_not_called()
        assert await _providers(session_maker) == []

    async def test_empty_gateway_address_reports_unavailable(self, session_maker):
        result, probe_mock = await _scan(
            session_maker, {11434: _ollama_models()},
            env={"HOST_GATEWAY_ADDRESS": ""},
        )

        assert result["available"] is False
        probe_mock.assert_not_called()

    async def test_unavailable_scan_leaves_existing_detected_rows_alone(self, session_maker):
        """Unavailable is 'cannot tell', not 'nothing is there' — don't reconcile away."""
        await _scan(session_maker, {11434: _ollama_models()})

        await _scan(session_maker, {}, env={"CONTAINER_RUNTIME": "kubernetes"})

        assert len(await _providers(session_maker)) == 1
