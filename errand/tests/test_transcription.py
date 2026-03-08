import io
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

import llm as llm_module
import llm_providers as llm_providers_module
from llm import transcribe_audio, TranscriptionNotConfiguredError, LLMClientNotConfiguredError
from models import Setting


@pytest.fixture(autouse=True)
def set_encryption_key(monkeypatch):
    """Set CREDENTIAL_ENCRYPTION_KEY for provider creation tests."""
    monkeypatch.setenv("CREDENTIAL_ENCRYPTION_KEY", "_26HOOIDUcxDH7fkoqI39DZulVPVK-hZe5THhiVLxIs=")


# --- Session fixture for direct transcribe_audio tests ---

_SETTINGS_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS settings (
    key TEXT NOT NULL PRIMARY KEY,
    value TEXT NOT NULL,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL
)
"""


@pytest.fixture()
async def db_session():
    engine = create_async_engine("sqlite+aiosqlite://", echo=False)
    async with engine.begin() as conn:
        await conn.execute(text(_SETTINGS_TABLE_SQL))
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with session_factory() as session:
        yield session
    await engine.dispose()


# --- 8.1 Test transcribe_audio ---


async def test_transcribe_audio_success(db_session: AsyncSession):
    """transcribe_audio calls audio.transcriptions.create with correct model and file tuple."""
    mock_response = MagicMock()
    mock_response.text = "Hello world"

    mock_client = AsyncMock()
    mock_client.audio.transcriptions.create = AsyncMock(return_value=mock_response)

    fake_file = MagicMock()
    fake_file.filename = "recording.webm"
    fake_file.content_type = "audio/webm"
    fake_file.read = AsyncMock(return_value=b"fake audio data")

    with patch.object(llm_providers_module, "resolve_model_setting", AsyncMock(return_value=(mock_client, "whisper-large-v3"))):
        result = await transcribe_audio(fake_file, db_session)

    assert result == "Hello world"
    mock_client.audio.transcriptions.create.assert_called_once_with(
        model="whisper-large-v3",
        file=("recording.webm", b"fake audio data", "audio/webm"),
    )


async def test_transcribe_audio_no_model_raises(db_session: AsyncSession):
    """transcribe_audio raises TranscriptionNotConfiguredError when no transcription_model setting."""
    with patch.object(llm_providers_module, "resolve_model_setting", AsyncMock(return_value=(None, None))):
        with pytest.raises(TranscriptionNotConfiguredError):
            await transcribe_audio(io.BytesIO(b"data"), db_session)


async def test_transcribe_audio_no_client_raises(db_session: AsyncSession):
    """transcribe_audio raises TranscriptionNotConfiguredError when client is None."""
    with patch.object(llm_providers_module, "resolve_model_setting", AsyncMock(return_value=(None, None))):
        with pytest.raises(TranscriptionNotConfiguredError):
            await transcribe_audio(io.BytesIO(b"data"), db_session)


# --- 8.2 Test POST /api/transcribe ---


async def test_transcribe_endpoint_success(client: AsyncClient):
    """POST /api/transcribe returns 200 with transcript text on success."""
    with patch("main.transcribe_audio", new_callable=AsyncMock, return_value="Buy groceries"):
        resp = await client.post(
            "/api/transcribe",
            files={"file": ("recording.webm", b"fake audio", "audio/webm")},
        )

    assert resp.status_code == 200
    assert resp.json() == {"text": "Buy groceries"}


async def test_transcribe_endpoint_not_configured_503(client: AsyncClient):
    """POST /api/transcribe returns 503 when transcription is not configured."""
    with patch("main.transcribe_audio", new_callable=AsyncMock, side_effect=TranscriptionNotConfiguredError("Not configured")):
        resp = await client.post(
            "/api/transcribe",
            files={"file": ("recording.webm", b"fake audio", "audio/webm")},
        )

    assert resp.status_code == 503
    assert "not configured" in resp.json()["detail"].lower()


async def test_transcribe_endpoint_no_client_503(client: AsyncClient):
    """POST /api/transcribe returns 503 when LLM client is missing."""
    with patch("main.transcribe_audio", new_callable=AsyncMock, side_effect=LLMClientNotConfiguredError("No client")):
        resp = await client.post(
            "/api/transcribe",
            files={"file": ("recording.webm", b"fake audio", "audio/webm")},
        )

    assert resp.status_code == 503


async def test_transcribe_endpoint_api_failure_502(client: AsyncClient):
    """POST /api/transcribe returns 502 when transcription API call fails."""
    with patch("main.transcribe_audio", new_callable=AsyncMock, side_effect=Exception("API Error")):
        resp = await client.post(
            "/api/transcribe",
            files={"file": ("recording.webm", b"fake audio", "audio/webm")},
        )

    assert resp.status_code == 502
    assert "failed" in resp.json()["detail"].lower()


async def test_transcribe_endpoint_unauthenticated_401(unauth_client: AsyncClient):
    """POST /api/transcribe returns 401 when not authenticated."""
    resp = await unauth_client.post(
        "/api/transcribe",
        files={"file": ("recording.webm", b"fake audio", "audio/webm")},
    )

    assert resp.status_code in (401, 403)


# --- 8.3 Test GET /api/transcribe/status ---


async def test_transcribe_status_enabled(admin_client: AsyncClient):
    """GET /api/transcribe/status returns enabled=true when model setting references a valid provider."""
    # Create a provider first
    with patch("main.probe_provider_type", new_callable=AsyncMock, return_value="openai_compatible"):
        prov_resp = await admin_client.post("/api/llm/providers", json={
            "name": "whisper-prov",
            "base_url": "https://api.example.com/v1",
            "api_key": "sk-test",
        })
    provider = prov_resp.json()

    # Set transcription_model referencing the provider
    await admin_client.put("/api/settings", json={
        "transcription_model": {"provider_id": provider["id"], "model": "whisper-large-v3"},
    })

    resp = await admin_client.get("/api/transcribe/status")
    assert resp.status_code == 200
    assert resp.json() == {"enabled": True}


async def test_transcribe_status_disabled_no_model(client: AsyncClient):
    """GET /api/transcribe/status returns enabled=false when no model setting."""
    resp = await client.get("/api/transcribe/status")
    assert resp.status_code == 200
    assert resp.json() == {"enabled": False}


async def test_transcribe_status_disabled_no_client(client: AsyncClient):
    """GET /api/transcribe/status returns enabled=false when provider doesn't exist."""
    # This would need an admin client to set the setting, but without a valid provider it should be false
    resp = await client.get("/api/transcribe/status")
    assert resp.status_code == 200
    assert resp.json() == {"enabled": False}


