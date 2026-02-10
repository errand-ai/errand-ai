import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import AsyncClient

import llm as llm_module

VALID_STATUSES = ["new", "scheduled", "pending", "running", "review", "completed"]
VALID_CATEGORIES = ["immediate", "scheduled", "repeating"]


async def create_task(client: AsyncClient, input_text: str = "Test task") -> dict:
    resp = await client.post("/api/tasks", json={"input": input_text})
    assert resp.status_code == 201
    return resp.json()


def _mock_json_response(title: str, category: str = "immediate", execute_at=None, repeat_interval=None, repeat_until=None) -> MagicMock:
    """Create a mock LLM response with JSON content."""
    data = {"title": title, "category": category, "execute_at": execute_at, "repeat_interval": repeat_interval, "repeat_until": repeat_until}
    choice = MagicMock()
    choice.message.content = json.dumps(data)
    response = MagicMock()
    response.choices = [choice]
    return response


# --- GET /api/tasks ---


async def test_list_tasks_empty(client: AsyncClient):
    resp = await client.get("/api/tasks")
    assert resp.status_code == 200
    assert resp.json() == []


async def test_list_tasks_ordered_by_creation_desc(client: AsyncClient):
    t1 = await create_task(client, "First")
    t2 = await create_task(client, "Second")
    resp = await client.get("/api/tasks")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 2
    assert data[0]["id"] == t2["id"]
    assert data[1]["id"] == t1["id"]


# --- POST /api/tasks ---


async def test_create_task_short_input(client: AsyncClient):
    """Short input (<=5 words) becomes the title directly with Needs Info tag."""
    resp = await client.post("/api/tasks", json={"input": "Run analysis"})
    assert resp.status_code == 201
    data = resp.json()
    assert data["title"] == "Run analysis"
    assert data["status"] == "new"
    assert data["description"] is None
    assert data["category"] == "immediate"
    assert "Needs Info" in data["tags"]


async def test_create_task_missing_input(client: AsyncClient):
    resp = await client.post("/api/tasks", json={})
    assert resp.status_code == 422


async def test_create_task_empty_input(client: AsyncClient):
    resp = await client.post("/api/tasks", json={"input": ""})
    assert resp.status_code == 422


async def test_create_task_response_includes_categorisation_fields(client: AsyncClient):
    """Every task response includes category, execute_at, repeat_interval, repeat_until."""
    task = await create_task(client, "Quick task")
    assert "category" in task
    assert "execute_at" in task
    assert "repeat_interval" in task
    assert "repeat_until" in task


# --- Auto-routing ---


async def test_auto_route_immediate_to_pending(client: AsyncClient):
    """Immediate task without Needs Info moves to pending."""
    mock_client = AsyncMock()
    mock_client.chat.completions.create = AsyncMock(
        return_value=_mock_json_response("Fix Bug", "immediate")
    )

    with patch.object(llm_module, "_client", mock_client):
        resp = await client.post(
            "/api/tasks",
            json={"input": "We need to fix the critical authentication bug in production"},
        )

    assert resp.status_code == 201
    assert resp.json()["status"] == "pending"


async def test_auto_route_scheduled_to_scheduled(client: AsyncClient):
    """Scheduled task without Needs Info moves to scheduled."""
    mock_client = AsyncMock()
    mock_client.chat.completions.create = AsyncMock(
        return_value=_mock_json_response("Send Report", "scheduled", execute_at="2026-02-15T17:00:00Z")
    )

    with patch.object(llm_module, "_client", mock_client):
        resp = await client.post(
            "/api/tasks",
            json={"input": "Send the quarterly financial report to the board next Friday"},
        )

    assert resp.status_code == 201
    assert resp.json()["status"] == "scheduled"


async def test_auto_route_needs_info_stays_new(client: AsyncClient):
    """Task with Needs Info stays in new regardless of category."""
    resp = await client.post("/api/tasks", json={"input": "Fix login"})
    assert resp.status_code == 201
    data = resp.json()
    assert data["status"] == "new"
    assert "Needs Info" in data["tags"]


# --- GET /api/tasks/{id} ---


async def test_get_task_found(client: AsyncClient):
    task = await create_task(client, "Find me")
    resp = await client.get(f"/api/tasks/{task['id']}")
    assert resp.status_code == 200
    data = resp.json()
    assert data["title"] == "Find me"
    assert "category" in data
    assert "execute_at" in data


async def test_get_task_not_found(client: AsyncClient):
    resp = await client.get("/api/tasks/00000000-0000-0000-0000-000000000000")
    assert resp.status_code == 404


# --- PATCH /api/tasks/{id} ---


async def test_update_task_status(client: AsyncClient):
    task = await create_task(client)
    resp = await client.patch(f"/api/tasks/{task['id']}", json={"status": "scheduled"})
    assert resp.status_code == 200
    assert resp.json()["status"] == "scheduled"


async def test_update_task_title(client: AsyncClient):
    task = await create_task(client)
    resp = await client.patch(f"/api/tasks/{task['id']}", json={"title": "New title"})
    assert resp.status_code == 200
    assert resp.json()["title"] == "New title"


async def test_update_task_not_found(client: AsyncClient):
    resp = await client.patch(
        "/api/tasks/00000000-0000-0000-0000-000000000000", json={"title": "Nope"}
    )
    assert resp.status_code == 404


async def test_update_task_invalid_status(client: AsyncClient):
    task = await create_task(client)
    resp = await client.patch(f"/api/tasks/{task['id']}", json={"status": "invalid"})
    assert resp.status_code == 422


async def test_update_task_empty_title(client: AsyncClient):
    task = await create_task(client)
    resp = await client.patch(f"/api/tasks/{task['id']}", json={"title": ""})
    assert resp.status_code == 422


async def test_update_task_category(client: AsyncClient):
    """PATCH with category field updates the category."""
    task = await create_task(client)
    resp = await client.patch(f"/api/tasks/{task['id']}", json={"category": "scheduled"})
    assert resp.status_code == 200
    assert resp.json()["category"] == "scheduled"


async def test_update_task_execute_at(client: AsyncClient):
    """PATCH with execute_at field."""
    task = await create_task(client)
    resp = await client.patch(
        f"/api/tasks/{task['id']}", json={"execute_at": "2026-02-15T17:00:00Z"}
    )
    assert resp.status_code == 200
    assert resp.json()["execute_at"] is not None


async def test_update_task_repeat_interval(client: AsyncClient):
    """PATCH with repeat_interval field."""
    task = await create_task(client)
    resp = await client.patch(
        f"/api/tasks/{task['id']}", json={"repeat_interval": "1d"}
    )
    assert resp.status_code == 200
    assert resp.json()["repeat_interval"] == "1d"


async def test_update_task_repeat_until(client: AsyncClient):
    """PATCH with repeat_until field."""
    task = await create_task(client)
    resp = await client.patch(
        f"/api/tasks/{task['id']}", json={"repeat_until": "2026-03-31T00:00:00Z"}
    )
    assert resp.status_code == 200
    assert resp.json()["repeat_until"] is not None


async def test_update_task_invalid_category(client: AsyncClient):
    """PATCH with invalid category returns 422."""
    task = await create_task(client)
    resp = await client.patch(f"/api/tasks/{task['id']}", json={"category": "invalid"})
    assert resp.status_code == 422


@pytest.mark.parametrize("cat", VALID_CATEGORIES)
async def test_all_valid_categories_accepted(client: AsyncClient, cat: str):
    task = await create_task(client)
    resp = await client.patch(f"/api/tasks/{task['id']}", json={"category": cat})
    assert resp.status_code == 200
    assert resp.json()["category"] == cat


# --- Auto-promotion ---


async def test_auto_promotion_new_with_needs_info_description_and_execute_at(client: AsyncClient):
    """Task in new with Needs Info, PATCH with description + execute_at → scheduled, tag removed."""
    # Create short-input task (new + Needs Info)
    task = await create_task(client, "Fix login")
    assert task["status"] == "new"
    assert "Needs Info" in task["tags"]

    resp = await client.patch(
        f"/api/tasks/{task['id']}",
        json={"description": "Fix the login bug on mobile", "execute_at": "2026-02-15T17:00:00Z"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "scheduled"
    assert "Needs Info" not in data["tags"]


async def test_auto_promotion_description_only_stays_new(client: AsyncClient):
    """Description alone does not trigger promotion."""
    task = await create_task(client, "Fix login")
    resp = await client.patch(
        f"/api/tasks/{task['id']}",
        json={"description": "Some details"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "new"
    assert "Needs Info" in data["tags"]


async def test_auto_promotion_scheduling_only_stays_new(client: AsyncClient):
    """Scheduling fields alone do not trigger promotion."""
    task = await create_task(client, "Fix login")
    resp = await client.patch(
        f"/api/tasks/{task['id']}",
        json={"execute_at": "2026-02-15T17:00:00Z"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "new"
    assert "Needs Info" in data["tags"]


async def test_auto_promotion_non_new_task_unaffected(client: AsyncClient):
    """Auto-promotion only applies to tasks in new status."""
    task = await create_task(client, "Fix login")
    # Move to running first
    await client.patch(f"/api/tasks/{task['id']}", json={"status": "running"})

    resp = await client.patch(
        f"/api/tasks/{task['id']}",
        json={"description": "Details", "execute_at": "2026-02-15T17:00:00Z"},
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "running"


# --- Valid status enforcement ---


@pytest.mark.parametrize("status", VALID_STATUSES)
async def test_all_valid_statuses_accepted(client: AsyncClient, status: str):
    task = await create_task(client)
    resp = await client.patch(f"/api/tasks/{task['id']}", json={"status": status})
    assert resp.status_code == 200
    assert resp.json()["status"] == status


# --- DELETE /api/tasks/{id} ---


async def test_delete_task_success(client: AsyncClient):
    """DELETE returns 204 and task is gone."""
    task = await create_task(client, "Delete me")
    resp = await client.delete(f"/api/tasks/{task['id']}")
    assert resp.status_code == 204

    # Verify it's gone
    resp = await client.get(f"/api/tasks/{task['id']}")
    assert resp.status_code == 404


async def test_delete_task_not_found(client: AsyncClient):
    """DELETE on non-existent task returns 404."""
    resp = await client.delete("/api/tasks/00000000-0000-0000-0000-000000000000")
    assert resp.status_code == 404


async def test_delete_task_publishes_event(client: AsyncClient, fake_valkey):
    """DELETE publishes task_deleted event to Valkey."""
    task = await create_task(client, "Delete me")

    pubsub = fake_valkey.pubsub()
    await pubsub.subscribe("task_events")
    # Consume subscribe confirmation
    await pubsub.get_message(ignore_subscribe_messages=True, timeout=1.0)

    resp = await client.delete(f"/api/tasks/{task['id']}")
    assert resp.status_code == 204

    # Check published event
    msg = await pubsub.get_message(ignore_subscribe_messages=True, timeout=1.0)
    assert msg is not None
    data = json.loads(msg["data"])
    assert data["event"] == "task_deleted"
    assert data["task"]["id"] == task["id"]

    await pubsub.unsubscribe("task_events")
    await pubsub.aclose()
