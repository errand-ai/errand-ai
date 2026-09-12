"""Local AI detection — probing the host gateway for OpenAI-compatible runtimes.

The scan contacts a fixed enumeration of well-known endpoints, never a port
range, and registers what answers as a provider with source="detected". It
mirrors `scan_env_providers` in shape, including the reconciliation that
removes rows for runtimes that have gone away.
"""

import os
import uuid
from dataclasses import dataclass
from unittest.mock import AsyncMock, patch

import httpx
import pytest
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from llm_providers import encrypt_api_key
from local_ai_detection import (
    DETECTED_API_KEY,
    ENDPOINT_ANSWERED,
    ENDPOINT_ERROR,
    ENDPOINT_NO_ANSWER,
    ENDPOINT_UNAUTHORIZED,
    LOCAL_AI_CANDIDATES,
    adopt_local_runtime,
    candidate_ports,
    identify_runtime,
    probe_local_endpoint,
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


@dataclass(frozen=True)
class _Endpoint:
    """A fake runtime: the listing it serves, and the key it demands.

    ``api_key=None`` is a runtime that ignores Authorization entirely, which is
    what every keyless local runtime does.
    """

    models: dict | None = None
    api_key: str | None = None

    def accepts(self, key: str) -> bool:
        return self.api_key is None or key == self.api_key

    def serves_a_listing(self) -> bool:
        """Whether what it serves is an OpenAI-compatible model listing.

        The fake holds itself to the real probe's bar. A double that answers
        "present" to anything is a double whose unconfigured default is success
        — which cannot fail for the reason you most need it to.
        """
        return isinstance(self.models, dict) and isinstance(self.models.get("data"), list)


def _port_of(base_url: str) -> int:
    return int(base_url.split(":")[2].split("/")[0])


def _responders(responding: dict[int, dict | _Endpoint]):
    """Build endpoint/type probe fakes where only the given ports answer.

    A bare payload is shorthand for a keyless runtime, so the tests written
    before keys existed read unchanged.
    """
    endpoints = {
        port: value if isinstance(value, _Endpoint) else _Endpoint(models=value)
        for port, value in responding.items()
    }

    async def fake_probe_endpoint(base_url, api_key):
        endpoint = endpoints.get(_port_of(base_url))
        if endpoint is None:
            return ENDPOINT_NO_ANSWER, None
        if not endpoint.accepts(api_key):
            return ENDPOINT_UNAUTHORIZED, None
        if not endpoint.serves_a_listing():
            return ENDPOINT_NO_ANSWER, None
        return ENDPOINT_ANSWERED, endpoint.models

    async def fake_probe_type(base_url, api_key):
        endpoint = endpoints.get(_port_of(base_url))
        if endpoint is None or not endpoint.accepts(api_key) or not endpoint.serves_a_listing():
            return "unknown"
        return "openai_compatible"

    return fake_probe_endpoint, fake_probe_type


def _detection_env(env: dict | None = None) -> dict:
    environ = {
        "HOST_GATEWAY_ADDRESS": "host.docker.internal",
        # clear=True wipes the key the autouse fixture set, and encryption
        # is not what these tests are about.
        "CREDENTIAL_ENCRYPTION_KEY": os.environ["CREDENTIAL_ENCRYPTION_KEY"],
    }
    environ.update(env or {})
    return environ


async def _scan(session_maker, responding: dict[int, dict | _Endpoint], env: dict | None = None):
    """Run a scan against fake endpoints.

    The returned mock is the *endpoint* probe — the one call every candidate
    receives, whatever it answers.
    """
    probe_endpoint, probe_type = _responders(responding)
    with patch("local_ai_detection.probe_local_endpoint", side_effect=probe_endpoint) as probe_mock, \
            patch("local_ai_detection.probe_provider_type", side_effect=probe_type), \
            patch.dict("os.environ", _detection_env(env), clear=True):
        async with session_maker() as session:
            result = await scan_local_ai(session)
    return result, probe_mock


async def _unknown_type(base_url, api_key):
    """A type probe that fails independently of the listing probe."""
    return "unknown"


def _erroring(port: int):
    """An endpoint that answers with an HTTP error rather than not at all."""
    async def probe(base_url, api_key):
        return (ENDPOINT_ERROR, None) if _port_of(base_url) == port else (ENDPOINT_NO_ANSWER, None)
    return probe


async def _adopt(session_maker, responding, base_url, api_key, name=None):
    probe_endpoint, probe_type = _responders(responding)
    with patch("local_ai_detection.probe_local_endpoint", side_effect=probe_endpoint), \
            patch("local_ai_detection.probe_provider_type", side_effect=probe_type), \
            patch.dict("os.environ", _detection_env(), clear=True):
        async with session_maker() as session:
            return await adopt_local_runtime(session, base_url, api_key, name)


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

    def test_an_unread_response_is_not_named_after_the_ports_claimant(self):
        """A 401 carries no body. Naming the endpoint after whatever nominally
        claims its port would register an oMLX server on 8000 as `vllm`."""
        name = identify_runtime(None, port=8000)

        assert name != "vllm"
        assert "8000" in name

    def test_a_read_response_with_no_marker_still_uses_the_claimant(self):
        """The distinction is between "no body" and "a body carrying no marker"
        — the second is still a fair inference."""
        assert identify_runtime(_anonymous_models(), port=8000) == "vllm"

    def test_no_port_and_no_body_names_nothing(self):
        assert identify_runtime(None, port=None) == "local-ai"

    def test_an_mlx_server_names_itself(self):
        """Measured against a real oMLX server: `owned_by: "omlx"`."""
        omlx = {"object": "list", "data": [
            {"id": "Qwen3.8-27B-MLX-8bit", "owned_by": "omlx"},
        ]}

        assert identify_runtime(omlx, port=8000) == "omlx"

    def test_an_unrecognised_marker_does_not_fall_back_to_the_port(self):
        """A marker we do not know is the response saying it is not the port's
        usual occupant. Answering `vllm` would contradict what we just read —
        which is how an oMLX server on 8000 got registered as vLLM."""
        unknown = {"object": "list", "data": [{"id": "m", "owned_by": "something-new"}]}

        name = identify_runtime(unknown, port=8000)

        assert name != "vllm"
        assert "8000" in name

    def test_an_empty_marker_is_a_silence_not_a_claim(self):
        """`owned_by: ""` says nothing, so the port may still speak."""
        blank = {"object": "list", "data": [{"id": "m", "owned_by": ""}]}

        assert identify_runtime(blank, port=11434) == "ollama"

    def test_a_recognised_marker_wins_over_an_unrecognised_one(self):
        listing = {"object": "list", "data": [
            {"id": "a", "owned_by": "something-new"},
            {"id": "b", "owned_by": "library"},
        ]}

        assert identify_runtime(listing, port=8000) == "ollama"


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


# --- The endpoint probe ----------------------------------------------------


# Captured before any patching: the factory below must build a real client,
# and the patch target is the shared httpx module attribute.
_REAL_ASYNC_CLIENT = httpx.AsyncClient


def _mock_transport(handler):
    """Patch target that hands local_ai_detection a client with a fake transport."""

    def factory(*args, **kwargs):
        return _REAL_ASYNC_CLIENT(transport=httpx.MockTransport(handler))

    return patch("local_ai_detection.httpx.AsyncClient", factory)


class TestProbeLocalEndpoint:
    """Detection asks "is something OpenAI-compatible here", not "what type is it".

    `probe_provider_type()` answers the second question and four other call
    sites depend on `unknown` meaning what it means today, so this is a
    separate probe rather than a loosened one.
    """

    async def test_a_model_listing_is_an_answer(self):
        def handler(request):
            return httpx.Response(200, json=_ollama_models())

        with _mock_transport(handler):
            status, payload = await probe_local_endpoint("http://h:11434/v1", DETECTED_API_KEY)

        assert status == ENDPOINT_ANSWERED
        assert payload == _ollama_models()

    async def test_401_is_a_service_that_needs_a_key(self):
        def handler(request):
            return httpx.Response(401, json={"error": {"message": "API key required"}})

        with _mock_transport(handler):
            status, payload = await probe_local_endpoint("http://h:8000/v1", DETECTED_API_KEY)

        assert status == ENDPOINT_UNAUTHORIZED
        assert payload is None

    async def test_403_is_a_service_that_needs_a_key(self):
        def handler(request):
            return httpx.Response(403, json={"error": "forbidden"})

        with _mock_transport(handler):
            status, _ = await probe_local_endpoint("http://h:8000/v1", DETECTED_API_KEY)

        assert status == ENDPOINT_UNAUTHORIZED

    async def test_404_is_nothing_here(self):
        def handler(request):
            return httpx.Response(404)

        with _mock_transport(handler):
            status, _ = await probe_local_endpoint("http://h:1234/v1", DETECTED_API_KEY)

        assert status == ENDPOINT_NO_ANSWER

    async def test_a_connection_failure_is_nothing_here(self):
        def handler(request):
            raise httpx.ConnectError("refused")

        with _mock_transport(handler):
            status, _ = await probe_local_endpoint("http://h:1234/v1", DETECTED_API_KEY)

        assert status == ENDPOINT_NO_ANSWER

    async def test_an_unreadable_200_body_is_not_an_answer(self):
        """200 from something that is not an OpenAI-compatible listing."""
        def handler(request):
            return httpx.Response(200, text="<html>hello</html>")

        with _mock_transport(handler):
            status, payload = await probe_local_endpoint("http://h:8080/v1", DETECTED_API_KEY)

        assert status == ENDPOINT_NO_ANSWER
        assert payload is None

    async def test_a_json_object_that_is_not_a_listing_is_not_an_answer(self):
        """A 200 carrying JSON is not proof of an OpenAI-compatible service.

        Before this probe existed, `probe_provider_type()` resolved such an
        endpoint to `unknown` and detection skipped it. Accepting any JSON
        object here would register whatever happens to sit on a candidate port
        as a provider whose type is `unknown` — which the model-list route then
        refuses, so the row could never be used for anything.
        """
        for payload in ({}, {"foo": 1}, {"data": "not-a-list"}, {"data": {}}):
            def handler(request, payload=payload):
                return httpx.Response(200, json=payload)

            with _mock_transport(handler):
                status, body = await probe_local_endpoint("http://h:8080/v1", DETECTED_API_KEY)

            assert status == ENDPOINT_NO_ANSWER, f"{payload!r} was accepted as a listing"
            assert body is None

    async def test_an_empty_listing_is_still_a_listing(self):
        """A runtime with no models loaded is present and OpenAI-compatible."""
        def handler(request):
            return httpx.Response(200, json={"object": "list", "data": []})

        with _mock_transport(handler):
            status, body = await probe_local_endpoint("http://h:11434/v1", DETECTED_API_KEY)

        assert status == ENDPOINT_ANSWERED
        assert body == {"object": "list", "data": []}

    @pytest.mark.parametrize("status", [500, 502, 503, 429, 400])
    async def test_an_http_error_is_a_service_that_is_present(self, status):
        """A runtime that answers 503 is up and briefly unwell, not gone.

        Reconciliation deletes providers whose runtime has departed and clears
        the model settings that referenced them. Treating a transient error as
        absence turns a momentary blip into destroyed configuration — the same
        argument that makes a 401 proof of presence rather than absence.
        """
        def handler(request):
            return httpx.Response(status, text="upstream unavailable")

        with _mock_transport(handler):
            state, payload = await probe_local_endpoint("http://h:11434/v1", DETECTED_API_KEY)

        assert state == ENDPOINT_ERROR
        assert payload is None

    async def test_404_is_still_nothing_here(self):
        """Unchanged: 404 proves the endpoint does not exist."""
        def handler(request):
            return httpx.Response(404)

        with _mock_transport(handler):
            state, _ = await probe_local_endpoint("http://h:1234/v1", DETECTED_API_KEY)

        assert state == ENDPOINT_NO_ANSWER

    async def test_the_supplied_key_is_sent(self):
        seen = {}

        def handler(request):
            seen["auth"] = request.headers.get("Authorization")
            return httpx.Response(200, json=_ollama_models())

        with _mock_transport(handler):
            await probe_local_endpoint("http://h:8000/v1", "sk-mine")

        assert seen["auth"] == "Bearer sk-mine"


# --- Runtimes that require a key -------------------------------------------


class TestKeyRequiringRuntimes:
    async def test_unauthorised_candidate_is_reported_rather_than_skipped(self, session_maker):
        result, _ = await _scan(
            session_maker, {8000: _Endpoint(_anonymous_models(), api_key="sk-real")}
        )

        assert result["needs_key"] == [{"base_url": "http://host.docker.internal:8000/v1"}]

    async def test_no_provider_is_created_for_it(self, session_maker):
        """A row carrying the sentinel against a service that just rejected it
        would be a provider guaranteed to fail."""
        await _scan(session_maker, {8000: _Endpoint(_anonymous_models(), api_key="sk-real")})

        assert await _providers(session_maker) == []

    async def test_entry_asserts_no_runtime_name_or_type(self, session_maker):
        """A 401 carries no body, so nothing beyond the endpoint is known."""
        result, _ = await _scan(
            session_maker, {8000: _Endpoint(_anonymous_models(), api_key="sk-real")}
        )

        assert list(result["needs_key"][0].keys()) == ["base_url"]

    async def test_an_absent_endpoint_is_reported_as_neither(self, session_maker):
        result, _ = await _scan(
            session_maker, {8000: _Endpoint(_anonymous_models(), api_key="sk-real")}
        )

        # 8080, 11434 and the rest answered nothing at all.
        assert result["needs_key"] == [{"base_url": "http://host.docker.internal:8000/v1"}]
        assert result["detected"] == []

    async def test_keyed_and_keyless_are_reported_in_the_right_place(self, session_maker):
        result, _ = await _scan(session_maker, {
            11434: _ollama_models(),
            8000: _Endpoint(_anonymous_models(), api_key="sk-real"),
        })

        assert [d["name"] for d in result["detected"]] == ["ollama"]
        assert result["needs_key"] == [{"base_url": "http://host.docker.internal:8000/v1"}]
        assert [p.name for p in await _providers(session_maker)] == ["ollama"]

    async def test_base_urls_are_unique_within_a_result(self, session_maker):
        result, _ = await _scan(session_maker, {
            8000: _Endpoint(api_key="sk-a"),
            8080: _Endpoint(api_key="sk-b"),
        })

        urls = [e["base_url"] for e in result["needs_key"]]
        assert len(urls) == len(set(urls)) == 2

    async def test_a_non_listing_responder_is_not_registered(self, session_maker):
        """Whatever else is listening on a candidate port is not a provider."""
        result, _ = await _scan(session_maker, {8080: {"status": "healthy"}})

        assert result["detected"] == []
        assert result["needs_key"] == []
        assert await _providers(session_maker) == []

    async def test_nothing_found_at_all_reports_both_empty(self, session_maker):
        result, _ = await _scan(session_maker, {})

        assert result["available"] is True
        assert result["detected"] == []
        assert result["needs_key"] == []

    async def test_unavailable_reports_no_key_requiring_runtimes(self, session_maker):
        result, probe_mock = await _scan(
            session_maker, {8000: _Endpoint(api_key="sk-real")},
            env={"CONTAINER_RUNTIME": "kubernetes"},
        )

        assert result["available"] is False
        assert result["needs_key"] == []
        probe_mock.assert_not_called()


class TestNeedsKeyExclusion:
    """An endpoint already served by a provider is not offered for adoption."""

    async def test_adopted_endpoint_is_not_offered_again(self, session_maker):
        endpoints = {8000: _Endpoint(_anonymous_models(), api_key="sk-real")}
        await _adopt(session_maker, endpoints, "http://host.docker.internal:8000/v1", "sk-real")

        result, _ = await _scan(session_maker, endpoints)

        assert result["needs_key"] == []
        assert [d["base_url"] for d in result["detected"]] == [
            "http://host.docker.internal:8000/v1"
        ]

    async def test_an_adopted_endpoint_whose_key_was_rotated_is_not_offered_again(self, session_maker):
        """Replacing a key on a provider that exists is an edit, not an adoption."""
        await _adopt(
            session_maker,
            {8000: _Endpoint(_anonymous_models(), api_key="sk-old")},
            "http://host.docker.internal:8000/v1", "sk-old",
        )

        result, _ = await _scan(
            session_maker, {8000: _Endpoint(_anonymous_models(), api_key="sk-rotated")}
        )

        assert result["needs_key"] == []
        assert len(await _providers(session_maker)) == 1

    async def test_a_manually_configured_endpoint_is_not_offered(self, session_maker):
        async with session_maker() as session:
            session.add(LlmProvider(
                id=uuid.uuid4(),
                name="my-vllm",
                base_url="http://host.docker.internal:8000/v1",
                api_key_encrypted=encrypt_api_key("sk-real"),
                provider_type="openai_compatible",
                is_default=True,
                source="database",
            ))
            await session.commit()

        result, _ = await _scan(session_maker, {8000: _Endpoint(api_key="sk-real")})

        assert result["needs_key"] == []


# --- Adoption --------------------------------------------------------------


class TestAdoption:
    URL = "http://host.docker.internal:8000/v1"

    async def test_an_accepted_key_creates_a_detected_provider(self, session_maker):
        from llm_providers import decrypt_api_key

        result = await _adopt(
            session_maker,
            {8000: _Endpoint(_anonymous_models(), api_key="sk-real")},
            self.URL, "sk-real",
        )

        assert result["adopted"] is True
        providers = await _providers(session_maker)
        assert len(providers) == 1
        assert providers[0].source == "detected"
        assert providers[0].base_url == self.URL
        assert decrypt_api_key(providers[0].api_key_encrypted) == "sk-real"
        assert result["provider"]["id"] == str(providers[0].id)

    async def test_the_name_comes_from_the_keyed_response(self, session_maker):
        """Not from the candidate table: 8000 is vLLM's port, but this is not vLLM."""
        omlx = {"object": "list", "data": [{"id": "qwen", "owned_by": "library"}]}

        result = await _adopt(
            session_maker, {8000: _Endpoint(omlx, api_key="sk-real")}, self.URL, "sk-real",
        )

        assert result["provider"]["name"] == "ollama"

    async def test_an_unidentifiable_keyed_response_is_not_named_after_the_port(self, session_maker):
        """A response read but carrying no marker still uses the port's single
        claimant — that inference is fair once a body has been read."""
        result = await _adopt(
            session_maker,
            {11434: _Endpoint(_anonymous_models(), api_key="sk-real")},
            "http://host.docker.internal:11434/v1", "sk-real",
        )

        assert result["provider"]["name"] == "ollama"

    async def test_a_rejected_key_creates_nothing_and_says_so(self, session_maker):
        result = await _adopt(
            session_maker, {8000: _Endpoint(api_key="sk-real")}, self.URL, "sk-wrong",
        )

        assert result["adopted"] is False
        assert result["reason"] == "key_rejected"
        assert result["message"]
        assert await _providers(session_maker) == []

    async def test_an_unreachable_endpoint_creates_nothing_and_says_so(self, session_maker):
        result = await _adopt(session_maker, {}, self.URL, "sk-real")

        assert result["adopted"] is False
        assert result["reason"] == "unreachable"
        assert await _providers(session_maker) == []

    async def test_a_taken_name_is_refused_with_the_name_that_is_taken(self, session_maker):
        async with session_maker() as session:
            session.add(LlmProvider(
                id=uuid.uuid4(), name="ollama", base_url="https://elsewhere.example/v1",
                api_key_encrypted=encrypt_api_key("sk-x"), provider_type="openai_compatible",
                is_default=True, source="database",
            ))
            await session.commit()

        result = await _adopt(
            session_maker, {8000: _Endpoint(_ollama_models(), api_key="sk-real")},
            self.URL, "sk-real",
        )

        assert result["adopted"] is False
        assert result["reason"] == "name_conflict"
        assert result["conflicting_name"] == "ollama"
        assert len(await _providers(session_maker)) == 1

    async def test_a_caller_supplied_name_resolves_a_conflict(self, session_maker):
        async with session_maker() as session:
            session.add(LlmProvider(
                id=uuid.uuid4(), name="ollama", base_url="https://elsewhere.example/v1",
                api_key_encrypted=encrypt_api_key("sk-x"), provider_type="openai_compatible",
                is_default=True, source="database",
            ))
            await session.commit()

        result = await _adopt(
            session_maker, {8000: _Endpoint(_ollama_models(), api_key="sk-real")},
            self.URL, "sk-real", name="my-omlx",
        )

        assert result["adopted"] is True
        assert result["provider"]["name"] == "my-omlx"

    async def test_a_trailing_slash_is_normalised_before_storing(self, session_maker):
        """The scan constructs `.../v1` and matches detected providers by exact
        string. Storing `.../v1/` verbatim means the next scan misses the stored
        key, offers the canonical endpoint for adoption again, and deletes this
        row as departed — taking its model settings with it. The same data loss
        D4 and the endpoint lock exist to prevent, reached by a third route.
        """
        endpoints = {8000: _Endpoint(_anonymous_models(), api_key="sk-real")}

        result = await _adopt(session_maker, endpoints, self.URL + "/", "sk-real")

        assert result["adopted"] is True
        assert (await _providers(session_maker))[0].base_url == self.URL

    async def test_an_endpoint_adopted_with_a_trailing_slash_survives_a_rescan(self, session_maker):
        endpoints = {8000: _Endpoint(_anonymous_models(), api_key="sk-real")}
        await _adopt(session_maker, endpoints, self.URL + "/", "sk-real")
        adopted = (await _providers(session_maker))[0]

        result, _ = await _scan(session_maker, endpoints)

        providers = await _providers(session_maker)
        assert len(providers) == 1, "the adopted provider was reconciled away"
        assert providers[0].id == adopted.id
        assert result["needs_key"] == [], "its endpoint was offered for adoption again"

    async def test_a_non_listing_responder_cannot_be_adopted(self, session_maker):
        result = await _adopt(session_maker, {8000: {"status": "healthy"}}, self.URL, "sk-real")

        assert result["adopted"] is False
        assert result["reason"] == "unreachable"
        assert await _providers(session_maker) == []

    async def test_an_endpoint_that_already_has_a_provider_is_not_adopted_twice(self, session_maker):
        """`base_url` is a detected provider's identity — D4, the endpoint lock
        and URL normalisation all rest on that. Two rows at one endpoint
        contradicts it, and the scan's lookup then raises, 500ing every
        subsequent scan until a human deletes a row by hand.
        """
        endpoints = {8000: _Endpoint(_anonymous_models(), api_key="sk-real")}
        await _adopt(session_maker, endpoints, self.URL, "sk-real")

        result = await _adopt(session_maker, endpoints, self.URL, "sk-real")

        assert result["adopted"] is False
        assert result["reason"] == "already_configured"
        assert len(await _providers(session_maker)) == 1

    async def test_a_supplied_name_does_not_bypass_the_endpoint_check(self, session_maker):
        """The name was the only thing standing between this and a duplicate."""
        endpoints = {8000: _Endpoint(_anonymous_models(), api_key="sk-real")}
        await _adopt(session_maker, endpoints, self.URL, "sk-real")

        result = await _adopt(session_maker, endpoints, self.URL, "sk-real", name="something-else")

        assert result["adopted"] is False
        assert result["reason"] == "already_configured"
        assert len(await _providers(session_maker)) == 1

    async def test_an_endpoint_held_by_a_manual_provider_is_not_adopted(self, session_maker):
        """Consistent with needs_key exclusion, which is source-blind."""
        async with session_maker() as session:
            session.add(LlmProvider(
                id=uuid.uuid4(), name="mine", base_url=self.URL,
                api_key_encrypted=encrypt_api_key("sk-x"), provider_type="openai_compatible",
                is_default=True, source="database",
            ))
            await session.commit()

        result = await _adopt(
            session_maker, {8000: _Endpoint(_anonymous_models(), api_key="sk-real")},
            self.URL, "sk-real",
        )

        assert result["adopted"] is False
        assert result["reason"] == "already_configured"
        assert len(await _providers(session_maker)) == 1

    async def test_a_trailing_slash_does_not_evade_the_endpoint_check(self, session_maker):
        endpoints = {8000: _Endpoint(_anonymous_models(), api_key="sk-real")}
        await _adopt(session_maker, endpoints, self.URL, "sk-real")

        result = await _adopt(session_maker, endpoints, self.URL + "/", "sk-real")

        assert result["adopted"] is False
        assert len(await _providers(session_maker)) == 1

    async def test_a_non_candidate_endpoint_cannot_be_adopted(self, session_maker):
        """Reconciliation only probes the candidate table. A detected row at an
        endpoint no scan visits is deleted on the next scan, taking its model
        settings — so adoption must not create one. It also stops a
        caller-supplied key being sent to any host the caller names.
        """
        with pytest.raises(ValueError):
            await _adopt(
                session_maker, {9999: _Endpoint(_anonymous_models(), api_key="sk-real")},
                "http://host.docker.internal:9999/v1", "sk-real",
            )

        assert await _providers(session_maker) == []

    async def test_an_endpoint_on_another_host_cannot_be_adopted(self, session_maker):
        with pytest.raises(ValueError):
            await _adopt(
                session_maker, {8000: _Endpoint(_anonymous_models(), api_key="sk-real")},
                "http://evil.example:8000/v1", "sk-real",
            )

        assert await _providers(session_maker) == []

    async def test_a_type_probe_that_disagrees_does_not_yield_an_unusable_provider(self, session_maker):
        """The listing succeeded, so the endpoint is OpenAI-compatible. If the
        separate type probe times out, recording `unknown` produces a provider
        the model-list route refuses."""
        endpoints = {8000: _Endpoint(_anonymous_models(), api_key="sk-real")}
        probe_endpoint, _ = _responders(endpoints)
        with patch("local_ai_detection.probe_local_endpoint", side_effect=probe_endpoint), \
                patch("local_ai_detection.probe_provider_type", new=_unknown_type), \
                patch.dict("os.environ", _detection_env(), clear=True):
            async with session_maker() as session:
                result = await adopt_local_runtime(session, self.URL, "sk-real", None)

        assert result["adopted"] is True
        assert result["provider"]["provider_type"] == "openai_compatible"

    async def test_adoption_reconciles_nothing(self, session_maker):
        """No scan, and no existing provider removed — including a detected one
        whose runtime is not answering during this call."""
        await _scan(session_maker, {11434: _ollama_models()})
        assert len(await _providers(session_maker)) == 1

        await _adopt(
            session_maker, {8000: _Endpoint(_anonymous_models(), api_key="sk-real")},
            self.URL, "sk-real",
        )

        names = {p.base_url for p in await _providers(session_maker)}
        assert names == {"http://host.docker.internal:11434/v1", self.URL}

    async def test_the_first_provider_on_an_empty_install_becomes_default(self, session_maker):
        await _adopt(
            session_maker, {8000: _Endpoint(_anonymous_models(), api_key="sk-real")},
            self.URL, "sk-real",
        )

        assert (await _providers(session_maker))[0].is_default is True

    async def test_an_existing_default_is_preserved(self, session_maker):
        async with session_maker() as session:
            session.add(LlmProvider(
                id=uuid.uuid4(), name="my-proxy", base_url="https://proxy.example/v1",
                api_key_encrypted=encrypt_api_key("sk-x"), provider_type="litellm",
                is_default=True, source="database",
            ))
            await session.commit()

        await _adopt(
            session_maker, {8000: _Endpoint(_anonymous_models(), api_key="sk-real")},
            self.URL, "sk-real",
        )

        by_name = {p.name: p for p in await _providers(session_maker)}
        assert by_name["my-proxy"].is_default is True
        assert by_name["vllm"].is_default is False

    async def test_the_adopted_provider_gets_the_raised_detected_timeout(self, session_maker):
        """`source` is not a label here: a local runtime's first request loads
        model weights before producing a token, so the detected default is
        raised. Adopting as `database` would silently take that away."""
        from task_manager import DETECTED_PROVIDER_LLM_TIMEOUT

        await _adopt(
            session_maker, {8000: _Endpoint(_anonymous_models(), api_key="sk-real")},
            self.URL, "sk-real",
        )

        assert (await _providers(session_maker))[0].source == "detected"
        assert DETECTED_PROVIDER_LLM_TIMEOUT > 30


# --- Reconciliation with stored keys ---------------------------------------


class TestReconciliationWithStoredKeys:
    URL = "http://host.docker.internal:8000/v1"

    async def test_an_adopted_runtime_still_accepting_its_key_survives_a_rescan(self, session_maker):
        endpoints = {8000: _Endpoint(_anonymous_models(), api_key="sk-real")}
        await _adopt(session_maker, endpoints, self.URL, "sk-real")
        adopted = (await _providers(session_maker))[0]

        await _scan(session_maker, endpoints)
        await _scan(session_maker, endpoints)

        providers = await _providers(session_maker)
        assert len(providers) == 1
        assert providers[0].id == adopted.id

    async def test_a_rescan_does_not_overwrite_the_stored_key(self, session_maker):
        from llm_providers import decrypt_api_key

        endpoints = {8000: _Endpoint(_anonymous_models(), api_key="sk-real")}
        await _adopt(session_maker, endpoints, self.URL, "sk-real")

        await _scan(session_maker, endpoints)

        stored = decrypt_api_key((await _providers(session_maker))[0].api_key_encrypted)
        assert stored == "sk-real", "the scan clobbered the adopted key with the sentinel"

    async def test_a_rotated_key_does_not_delete_the_provider(self, session_maker):
        await _adopt(
            session_maker, {8000: _Endpoint(_anonymous_models(), api_key="sk-old")},
            self.URL, "sk-old",
        )

        await _scan(session_maker, {8000: _Endpoint(_anonymous_models(), api_key="sk-rotated")})

        providers = await _providers(session_maker)
        assert len(providers) == 1, "a rotated key deleted the user's provider"
        assert providers[0].base_url == self.URL

    async def test_a_departed_keyed_runtime_is_reconciled_away(self, session_maker):
        await _adopt(
            session_maker, {8000: _Endpoint(_anonymous_models(), api_key="sk-real")},
            self.URL, "sk-real",
        )

        await _scan(session_maker, {})

        assert await _providers(session_maker) == []

    async def test_a_scan_survives_duplicate_rows_at_one_endpoint(self, session_maker):
        """Adoption can no longer create these, but an installation that ran a
        build where it could must not be left with a scan that raises forever.
        """
        for name in ("dup-a", "dup-b"):
            async with session_maker() as session:
                session.add(LlmProvider(
                    id=uuid.uuid4(), name=name, base_url=self.URL,
                    api_key_encrypted=encrypt_api_key("sk-real"),
                    provider_type="openai_compatible", is_default=False, source="detected",
                ))
                await session.commit()

        result, _ = await _scan(
            session_maker, {8000: _Endpoint(_anonymous_models(), api_key="sk-real")}
        )

        assert result["available"] is True
        names = {p.name for p in await _providers(session_maker)}
        assert names == {"dup-a", "dup-b"}, "a duplicate was silently deleted"
        assert result["needs_key"] == []

    async def test_a_transient_error_does_not_delete_the_provider(self, session_maker):
        """The runtime answered. It is present, however unhappily."""
        await _scan(session_maker, {11434: _ollama_models()})
        assert len(await _providers(session_maker)) == 1

        with patch("local_ai_detection.probe_local_endpoint",
                   side_effect=_erroring(11434)), \
                patch("local_ai_detection.probe_provider_type",
                      new=_unknown_type), \
                patch.dict("os.environ", _detection_env(), clear=True):
            async with session_maker() as session:
                result = await scan_local_ai(session)

        assert len(await _providers(session_maker)) == 1, "a 503 deleted the provider"
        assert result["needs_key"] == [], "an erroring endpoint is not offered for adoption"

    async def test_a_legacy_url_with_a_trailing_slash_is_still_matched(self, session_maker):
        """Detected rows never carried a trailing slash, but the update route
        accepted one on every release before this change, so a row edited that
        way exists in the wild. Comparing raw strings would probe it with the
        sentinel, see 401, and delete it as departed."""
        async with session_maker() as session:
            session.add(LlmProvider(
                id=uuid.uuid4(), name="legacy", base_url=self.URL + "/",
                api_key_encrypted=encrypt_api_key("sk-real"),
                provider_type="openai_compatible", is_default=False, source="detected",
            ))
            await session.commit()

        result, probe_mock = await _scan(
            session_maker, {8000: _Endpoint(_anonymous_models(), api_key="sk-real")}
        )

        assert len(await _providers(session_maker)) == 1, "the legacy row was deleted"
        assert result["needs_key"] == [], "its endpoint was offered for adoption"
        by_url = {c.args[0]: c.args[1] for c in probe_mock.call_args_list}
        assert by_url[self.URL] == "sk-real", "its stored key was not used"

    async def test_a_manual_provider_with_a_trailing_slash_is_not_offered(self, session_maker):
        async with session_maker() as session:
            session.add(LlmProvider(
                id=uuid.uuid4(), name="mine", base_url=self.URL + "/",
                api_key_encrypted=encrypt_api_key("sk-x"),
                provider_type="openai_compatible", is_default=True, source="database",
            ))
            await session.commit()

        result, _ = await _scan(session_maker, {8000: _Endpoint(api_key="sk-real")})

        assert result["needs_key"] == []

    async def test_a_stored_key_is_sent_only_to_its_own_endpoint(self, session_maker):
        await _adopt(
            session_maker, {8000: _Endpoint(_anonymous_models(), api_key="sk-real")},
            self.URL, "sk-real",
        )

        _, probe_mock = await _scan(
            session_maker, {8000: _Endpoint(_anonymous_models(), api_key="sk-real")}
        )

        by_url = {call.args[0]: call.args[1] for call in probe_mock.call_args_list}
        assert by_url[self.URL] == "sk-real"
        others = {url: key for url, key in by_url.items() if url != self.URL}
        assert others, "no other candidate was probed"
        assert set(others.values()) == {DETECTED_API_KEY}


# --- The adoption endpoint -------------------------------------------------


def _adopt_patches(responding):
    """Patch detection's probes for a request through the API."""
    probe_endpoint, probe_type = _responders(responding)
    return (
        patch("local_ai_detection.probe_local_endpoint", side_effect=probe_endpoint),
        patch("local_ai_detection.probe_provider_type", side_effect=probe_type),
        patch.dict("os.environ", _detection_env(), clear=True),
    )


class TestAdoptEndpoint:
    URL = "http://host.docker.internal:8000/v1"

    async def test_a_working_key_adopts(self, admin_client):
        endpoint, ptype, environ = _adopt_patches(
            {8000: _Endpoint(_anonymous_models(), api_key="sk-real")}
        )
        with endpoint, ptype, environ:
            resp = await admin_client.post("/api/llm/providers/adopt-local", json={
                "base_url": self.URL, "api_key": "sk-real",
            })

        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["adopted"] is True
        assert body["provider"]["source"] == "detected"
        assert body["provider"]["base_url"] == self.URL

    async def test_a_rejected_key_is_a_finding_not_a_failure(self, admin_client):
        """200 with a machine-readable reason, matching the reachability check
        — the request was well formed and the probe ran."""
        endpoint, ptype, environ = _adopt_patches({8000: _Endpoint(api_key="sk-real")})
        with endpoint, ptype, environ:
            resp = await admin_client.post("/api/llm/providers/adopt-local", json={
                "base_url": self.URL, "api_key": "sk-wrong",
            })

        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["adopted"] is False
        assert body["reason"] == "key_rejected"
        assert body["message"]

    async def test_an_unreachable_endpoint_is_a_finding(self, admin_client):
        endpoint, ptype, environ = _adopt_patches({})
        with endpoint, ptype, environ:
            resp = await admin_client.post("/api/llm/providers/adopt-local", json={
                "base_url": self.URL, "api_key": "sk-real",
            })

        assert resp.status_code == 200
        assert resp.json()["reason"] == "unreachable"

    async def test_a_name_conflict_names_the_conflict(self, admin_client):
        endpoint, ptype, environ = _adopt_patches(
            {8000: _Endpoint(_ollama_models(), api_key="sk-real")}
        )
        with patch("main.probe_provider_type", new_callable=AsyncMock,
                   return_value="openai_compatible"):
            await admin_client.post("/api/llm/providers", json={
                "name": "ollama", "base_url": "https://elsewhere.example/v1",
                "api_key": "sk-x",
            })
        with endpoint, ptype, environ:
            resp = await admin_client.post("/api/llm/providers/adopt-local", json={
                "base_url": self.URL, "api_key": "sk-real",
            })

        body = resp.json()
        assert resp.status_code == 200
        assert body["adopted"] is False
        assert body["reason"] == "name_conflict"
        assert body["conflicting_name"] == "ollama"

    async def test_resubmitting_with_a_name_succeeds(self, admin_client):
        endpoint, ptype, environ = _adopt_patches(
            {8000: _Endpoint(_ollama_models(), api_key="sk-real")}
        )
        with patch("main.probe_provider_type", new_callable=AsyncMock,
                   return_value="openai_compatible"):
            await admin_client.post("/api/llm/providers", json={
                "name": "ollama", "base_url": "https://elsewhere.example/v1",
                "api_key": "sk-x",
            })
        with endpoint, ptype, environ:
            resp = await admin_client.post("/api/llm/providers/adopt-local", json={
                "base_url": self.URL, "api_key": "sk-real", "name": "my-omlx",
            })

        assert resp.json()["adopted"] is True
        assert resp.json()["provider"]["name"] == "my-omlx"

    async def test_the_stored_key_is_masked_in_the_response(self, admin_client):
        endpoint, ptype, environ = _adopt_patches(
            {8000: _Endpoint(_anonymous_models(), api_key="sk-supersecret")}
        )
        with endpoint, ptype, environ:
            resp = await admin_client.post("/api/llm/providers/adopt-local", json={
                "base_url": self.URL, "api_key": "sk-supersecret",
            })

        assert resp.json()["provider"]["api_key"] == "sk-s****"

    async def test_malformed_input_is_still_rejected(self, admin_client):
        resp = await admin_client.post("/api/llm/providers/adopt-local", json={
            "base_url": self.URL,
        })
        assert resp.status_code == 422

        resp = await admin_client.post("/api/llm/providers/adopt-local", json={
            "base_url": "", "api_key": "sk-real",
        })
        assert resp.status_code == 422

    async def test_requires_admin(self, client):
        resp = await client.post("/api/llm/providers/adopt-local", json={
            "base_url": self.URL, "api_key": "sk-real",
        })
        assert resp.status_code == 403


class TestDetectedProviderEndpointIsServerEnforced:
    """The settings card locks a detected provider's base URL. A guarantee that
    lives only in the caller is decorative: editing it through the API points
    the row at an endpoint the scan will not match, so the next scan reconciles
    it away and clears the model settings that referenced it."""

    async def _adopted_provider(self, admin_client):
        endpoint, ptype, environ = _adopt_patches(
            {8000: _Endpoint(_anonymous_models(), api_key="sk-real")}
        )
        with endpoint, ptype, environ:
            resp = await admin_client.post("/api/llm/providers/adopt-local", json={
                "base_url": "http://host.docker.internal:8000/v1", "api_key": "sk-real",
            })
        return resp.json()["provider"]

    async def test_changing_the_endpoint_is_refused(self, admin_client):
        provider = await self._adopted_provider(admin_client)

        resp = await admin_client.put(f"/api/llm/providers/{provider['id']}", json={
            "base_url": "http://elsewhere.example/v1",
        })

        assert resp.status_code == 403
        assert "reconciled by scanning" in resp.json()["detail"]

    async def test_renaming_is_not_refused(self, admin_client):
        """The name is the user's to change; only the endpoint is identity."""
        provider = await self._adopted_provider(admin_client)

        resp = await admin_client.put(f"/api/llm/providers/{provider['id']}", json={
            "name": "my-local-box",
        })

        assert resp.status_code == 200, resp.text
        assert resp.json()["name"] == "my-local-box"

    async def test_resubmitting_the_same_endpoint_is_not_a_change(self, admin_client):
        """A card that PUTs the whole form back must not be refused for
        including the field it correctly left alone."""
        provider = await self._adopted_provider(admin_client)

        resp = await admin_client.put(f"/api/llm/providers/{provider['id']}", json={
            "name": "renamed", "base_url": provider["base_url"],
        })

        assert resp.status_code == 200, resp.text

    async def test_a_database_provider_may_still_be_repointed(self, admin_client):
        with patch("main.probe_provider_type", new_callable=AsyncMock,
                   return_value="openai_compatible"):
            created = (await admin_client.post("/api/llm/providers", json={
                "name": "mine", "base_url": "https://a.example/v1", "api_key": "sk-x",
            })).json()

            resp = await admin_client.put(f"/api/llm/providers/{created['id']}", json={
                "base_url": "https://b.example/v1",
            })

        assert resp.status_code == 200, resp.text
        assert resp.json()["base_url"] == "https://b.example/v1"


class TestTheCardCanReachTheseRoutes:
    """The verbs the shipped settings card actually sends.

    `createDirectApi` issues PATCH to update a provider and POST to set the
    default, while the server registered only PUT — so renaming a provider,
    replacing its key and setting the default all returned 405 from the
    settings UI. The seam test cannot catch this: it injects a mock API object,
    so the library's HTTP layer is never exercised, and it guards response
    shapes rather than verbs.

    This matters to the endpoint lock above in particular: a server-side
    guarantee on a route the caller cannot reach is a guarantee that never
    runs.
    """

    async def _provider(self, admin_client):
        with patch("main.probe_provider_type", new_callable=AsyncMock,
                   return_value="openai_compatible"):
            resp = await admin_client.post("/api/llm/providers", json={
                "name": "p", "base_url": "https://a.example/v1", "api_key": "sk-x",
            })
        return resp.json()

    @pytest.mark.parametrize("method", ["PUT", "PATCH"])
    async def test_a_provider_can_be_updated_by_either_verb(self, admin_client, method):
        provider = await self._provider(admin_client)

        resp = await admin_client.request(
            method, f"/api/llm/providers/{provider['id']}", json={"name": f"via-{method}"},
        )

        assert resp.status_code == 200, resp.text
        assert resp.json()["name"] == f"via-{method}"

    @pytest.mark.parametrize("method", ["PUT", "POST"])
    async def test_the_default_can_be_set_by_either_verb(self, admin_client, method):
        first = await self._provider(admin_client)
        with patch("main.probe_provider_type", new_callable=AsyncMock,
                   return_value="openai_compatible"):
            second = (await admin_client.post("/api/llm/providers", json={
                "name": f"second-{method}", "base_url": "https://b.example/v1",
                "api_key": "sk-y",
            })).json()
        assert first["is_default"] is True

        resp = await admin_client.request(
            method, f"/api/llm/providers/{second['id']}/default",
        )

        assert resp.status_code == 200, resp.text
        assert resp.json()["is_default"] is True

    async def test_the_endpoint_lock_holds_on_the_verb_the_card_sends(self, admin_client):
        """The whole point of moving the constraint to the server."""
        endpoint, ptype, environ = _adopt_patches(
            {8000: _Endpoint(_anonymous_models(), api_key="sk-real")}
        )
        with endpoint, ptype, environ:
            adopted = (await admin_client.post("/api/llm/providers/adopt-local", json={
                "base_url": "http://host.docker.internal:8000/v1", "api_key": "sk-real",
            })).json()["provider"]

        resp = await admin_client.patch(f"/api/llm/providers/{adopted['id']}", json={
            "base_url": "http://elsewhere.example/v1",
        })

        assert resp.status_code == 403
        assert "reconciled by scanning" in resp.json()["detail"]
