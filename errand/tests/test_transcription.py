import io
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

import llm as llm_module
from llm import transcribe_audio, TranscriptionNotConfiguredError, LLMClientNotConfiguredError
from models import Setting


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
    db_session.add(Setting(key="transcription_model", value="whisper-large-v3"))
    await db_session.commit()

    mock_response = MagicMock()
    mock_response.text = "Hello world"

    mock_client = AsyncMock()
    mock_client.audio.transcriptions.create = AsyncMock(return_value=mock_response)

    fake_file = MagicMock()
    fake_file.filename = "recording.webm"
    fake_file.content_type = "audio/webm"
    fake_file.read = AsyncMock(return_value=b"fake audio data")

    with patch.object(llm_module, "_client", mock_client):
        result = await transcribe_audio(fake_file, db_session)

    assert result == "Hello world"
    mock_client.audio.transcriptions.create.assert_called_once_with(
        model="whisper-large-v3",
        file=("recording.webm", b"fake audio data", "audio/webm"),
    )


async def test_transcribe_audio_no_model_raises(db_session: AsyncSession):
    """transcribe_audio raises TranscriptionNotConfiguredError when no transcription_model setting."""
    mock_client = AsyncMock()

    with patch.object(llm_module, "_client", mock_client):
        with pytest.raises(TranscriptionNotConfiguredError):
            await transcribe_audio(io.BytesIO(b"data"), db_session)


async def test_transcribe_audio_no_client_raises(db_session: AsyncSession):
    """transcribe_audio raises LLMClientNotConfiguredError when client is None."""
    with patch.object(llm_module, "_client", None):
        with pytest.raises(LLMClientNotConfiguredError):
            await transcribe_audio(io.BytesIO(b"data"), db_session)


# --- 8.2 Test POST /api/transcribe ---


async def test_transcribe_endpoint_success(client: AsyncClient):
    """POST /api/transcribe returns 200 with transcript text on success."""
    mock_response = MagicMock()
    mock_response.text = "Buy groceries"

    mock_client = AsyncMock()
    mock_client.audio.transcriptions.create = AsyncMock(return_value=mock_response)

    with patch.object(llm_module, "_client", mock_client):
        # Need to set the transcription_model setting
        await client.put("/api/settings", json={"transcription_model": "whisper-large-v3"})

    # Re-patch for the actual call (admin_client above sets the setting)
    # Since the client fixture uses non-admin override that rejects require_admin,
    # we need to use admin_client for settings. Let's just mock transcribe_audio directly.
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
    """GET /api/transcribe/status returns enabled=true when model setting exists and client configured."""
    # Set the transcription_model setting
    await admin_client.put("/api/settings", json={"transcription_model": "whisper-large-v3"})

    mock_client = AsyncMock()
    with patch.object(llm_module, "_client", mock_client):
        resp = await admin_client.get("/api/transcribe/status")

    assert resp.status_code == 200
    assert resp.json() == {"enabled": True}


async def test_transcribe_status_disabled_no_model(client: AsyncClient):
    """GET /api/transcribe/status returns enabled=false when no model setting."""
    mock_client = AsyncMock()
    with patch.object(llm_module, "_client", mock_client):
        resp = await client.get("/api/transcribe/status")

    assert resp.status_code == 200
    assert resp.json() == {"enabled": False}


async def test_transcribe_status_disabled_no_client(client: AsyncClient):
    """GET /api/transcribe/status returns enabled=false when LLM client not configured."""
    with patch.object(llm_module, "_client", None):
        resp = await client.get("/api/transcribe/status")

    assert resp.status_code == 200
    assert resp.json() == {"enabled": False}


# --- 8.4 Test GET /api/llm/transcription-models ---


async def test_transcription_models_success(admin_client: AsyncClient):
    """GET /api/llm/transcription-models returns filtered, sorted list."""
    model_info_response = {
        "data": [
            {
                "model_name": "whisper-large-v3",
                "model_info": {"mode": "audio_transcription"},
            },
            {
                "model_name": "gpt-4o",
                "model_info": {"mode": "chat"},
            },
            {
                "model_name": "whisper-1",
                "model_info": {"mode": "audio_transcription"},
            },
        ]
    }

    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = model_info_response
    mock_response.raise_for_status = MagicMock()

    with patch("main.httpx.AsyncClient") as MockHttpClient:
        mock_http = AsyncMock()
        mock_http.get = AsyncMock(return_value=mock_response)
        mock_http.__aenter__ = AsyncMock(return_value=mock_http)
        mock_http.__aexit__ = AsyncMock(return_value=False)
        MockHttpClient.return_value = mock_http

        with patch.dict("os.environ", {"OPENAI_BASE_URL": "http://litellm:4000/v1"}):
            resp = await admin_client.get("/api/llm/transcription-models")

    assert resp.status_code == 200
    data = resp.json()
    assert data == ["whisper-1", "whisper-large-v3"]


async def test_transcription_models_non_admin_403(client: AsyncClient):
    """GET /api/llm/transcription-models returns 403 for non-admin."""
    resp = await client.get("/api/llm/transcription-models")
    assert resp.status_code == 403


async def test_transcription_models_proxy_error_502(admin_client: AsyncClient):
    """GET /api/llm/transcription-models returns 502 when proxy is unreachable."""
    with patch("main.httpx.AsyncClient") as MockHttpClient:
        mock_http = AsyncMock()
        mock_http.get = AsyncMock(side_effect=Exception("Connection refused"))
        mock_http.__aenter__ = AsyncMock(return_value=mock_http)
        mock_http.__aexit__ = AsyncMock(return_value=False)
        MockHttpClient.return_value = mock_http

        with patch.dict("os.environ", {"OPENAI_BASE_URL": "http://litellm:4000/v1"}):
            resp = await admin_client.get("/api/llm/transcription-models")

    assert resp.status_code == 502


async def test_transcription_models_empty_list(admin_client: AsyncClient):
    """GET /api/llm/transcription-models returns empty list when no transcription models."""
    model_info_response = {
        "data": [
            {
                "model_name": "gpt-4o",
                "model_info": {"mode": "chat"},
            },
        ]
    }

    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = model_info_response
    mock_response.raise_for_status = MagicMock()

    with patch("main.httpx.AsyncClient") as MockHttpClient:
        mock_http = AsyncMock()
        mock_http.get = AsyncMock(return_value=mock_response)
        mock_http.__aenter__ = AsyncMock(return_value=mock_http)
        mock_http.__aexit__ = AsyncMock(return_value=False)
        MockHttpClient.return_value = mock_http

        with patch.dict("os.environ", {"OPENAI_BASE_URL": "http://litellm:4000/v1"}):
            resp = await admin_client.get("/api/llm/transcription-models")

    assert resp.status_code == 200
    assert resp.json() == []
