from unittest.mock import AsyncMock, MagicMock, patch

from httpx import AsyncClient

import llm as llm_module


async def create_task(client: AsyncClient, input_text: str = "Test task") -> dict:
    resp = await client.post("/api/tasks", json={"input": input_text})
    assert resp.status_code == 201
    return resp.json()


def _mock_llm_response(title: str) -> MagicMock:
    """Create a mock OpenAI chat completion response."""
    choice = MagicMock()
    choice.message.content = title
    response = MagicMock()
    response.choices = [choice]
    return response


# --- Task creation with LLM ---


async def test_create_task_long_input_calls_llm(client: AsyncClient):
    """Long input (>5 words) triggers LLM title generation, input becomes description."""
    mock_client = AsyncMock()
    mock_client.chat.completions.create = AsyncMock(
        return_value=_mock_llm_response("Fix Auth Bug")
    )

    with patch.object(llm_module, "_client", mock_client):
        resp = await client.post(
            "/api/tasks",
            json={"input": "We need to fix the authentication bug that prevents login on mobile devices"},
        )

    assert resp.status_code == 201
    data = resp.json()
    assert data["title"] == "Fix Auth Bug"
    assert data["description"] == "We need to fix the authentication bug that prevents login on mobile devices"
    assert "Needs Info" not in data["tags"]
    mock_client.chat.completions.create.assert_called_once()


async def test_create_task_short_input_no_llm(client: AsyncClient):
    """Short input (<=5 words) uses input as title directly, no LLM call."""
    mock_client = AsyncMock()

    with patch.object(llm_module, "_client", mock_client):
        resp = await client.post("/api/tasks", json={"input": "Fix login"})

    assert resp.status_code == 201
    data = resp.json()
    assert data["title"] == "Fix login"
    assert data["description"] is None
    assert "Needs Info" in data["tags"]
    mock_client.chat.completions.create.assert_not_called()


async def test_create_task_llm_failure_uses_fallback(client: AsyncClient):
    """When LLM fails, a fallback title is generated and Needs Info tag is applied."""
    mock_client = AsyncMock()
    mock_client.chat.completions.create = AsyncMock(side_effect=Exception("LLM timeout"))

    with patch.object(llm_module, "_client", mock_client):
        resp = await client.post(
            "/api/tasks",
            json={"input": "We need to fix the authentication bug that prevents login on mobile devices"},
        )

    assert resp.status_code == 201
    data = resp.json()
    # Fallback title is first 5 words + "..."
    assert data["title"] == "We need to fix the..."
    assert data["description"] == "We need to fix the authentication bug that prevents login on mobile devices"
    assert "Needs Info" in data["tags"]


async def test_create_task_llm_not_configured_uses_fallback(client: AsyncClient):
    """When LLM client is None, fallback title is used."""
    with patch.object(llm_module, "_client", None):
        resp = await client.post(
            "/api/tasks",
            json={"input": "This is a longer description that should trigger title generation"},
        )

    assert resp.status_code == 201
    data = resp.json()
    assert data["title"] == "This is a longer description..."
    assert data["description"] == "This is a longer description that should trigger title generation"
    assert "Needs Info" in data["tags"]


async def test_create_task_exactly_five_words_is_short(client: AsyncClient):
    """Exactly 5 words is treated as short input (title, no LLM)."""
    resp = await client.post("/api/tasks", json={"input": "one two three four five"})
    assert resp.status_code == 201
    data = resp.json()
    assert data["title"] == "one two three four five"
    assert data["description"] is None
    assert "Needs Info" in data["tags"]


async def test_create_task_six_words_triggers_llm(client: AsyncClient):
    """Six words triggers LLM title generation."""
    mock_client = AsyncMock()
    mock_client.chat.completions.create = AsyncMock(
        return_value=_mock_llm_response("Generated Title")
    )

    with patch.object(llm_module, "_client", mock_client):
        resp = await client.post(
            "/api/tasks", json={"input": "one two three four five six"}
        )

    assert resp.status_code == 201
    data = resp.json()
    assert data["title"] == "Generated Title"
    assert data["description"] == "one two three four five six"
    mock_client.chat.completions.create.assert_called_once()


# --- GET /api/llm/models ---


async def test_llm_models_admin_access(admin_client: AsyncClient):
    """Admin can list LLM models."""
    mock_client = AsyncMock()
    model1 = MagicMock()
    model1.id = "claude-haiku-4-5-20251001"
    model2 = MagicMock()
    model2.id = "gpt-4o"
    models_response = MagicMock()
    models_response.data = [model2, model1]
    mock_client.models.list = AsyncMock(return_value=models_response)

    with patch.object(llm_module, "_client", mock_client):
        resp = await admin_client.get("/api/llm/models")

    assert resp.status_code == 200
    data = resp.json()
    assert data == ["claude-haiku-4-5-20251001", "gpt-4o"]  # sorted


async def test_llm_models_non_admin_403(client: AsyncClient):
    """Non-admin gets 403 for LLM models endpoint."""
    resp = await client.get("/api/llm/models")
    assert resp.status_code == 403


async def test_llm_models_not_configured_503(admin_client: AsyncClient):
    """Returns 503 when LLM client is not configured."""
    with patch.object(llm_module, "_client", None):
        resp = await admin_client.get("/api/llm/models")

    assert resp.status_code == 503
    assert "not configured" in resp.json()["detail"]


async def test_llm_models_provider_error_502(admin_client: AsyncClient):
    """Returns 502 when LLM provider fails."""
    mock_client = AsyncMock()
    mock_client.models.list = AsyncMock(side_effect=Exception("Connection refused"))

    with patch.object(llm_module, "_client", mock_client):
        resp = await admin_client.get("/api/llm/models")

    assert resp.status_code == 502
    assert "Failed to fetch" in resp.json()["detail"]
