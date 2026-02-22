import json

import pytest
from httpx import AsyncClient


async def create_task(client: AsyncClient, input_text: str = "Test task") -> dict:
    resp = await client.post("/api/tasks", json={"input": input_text})
    assert resp.status_code == 201
    return resp.json()


async def test_create_task_response_includes_output(client: AsyncClient):
    """Task response includes the output and retry_count fields (defaults)."""
    task = await create_task(client, "Quick task")
    assert "output" in task
    assert task["output"] is None
    assert "retry_count" in task
    assert task["retry_count"] == 0


async def test_list_tasks_includes_output(client: AsyncClient):
    """List tasks response includes output field."""
    await create_task(client, "Task one")
    resp = await client.get("/api/tasks")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    assert "output" in data[0]
    assert data[0]["output"] is None


async def test_get_task_includes_output(client: AsyncClient):
    """Get single task response includes output field."""
    task = await create_task(client, "Task one")
    resp = await client.get(f"/api/tasks/{task['id']}")
    assert resp.status_code == 200
    assert "output" in resp.json()


async def test_update_task_output(client: AsyncClient):
    """PATCH with output field stores the output."""
    task = await create_task(client, "Task one")
    resp = await client.patch(
        f"/api/tasks/{task['id']}", json={"output": "Hello from container"}
    )
    assert resp.status_code == 200
    assert resp.json()["output"] == "Hello from container"


async def test_update_task_output_in_event(client: AsyncClient, fake_valkey):
    """task_updated event includes output field."""
    task = await create_task(client, "Task one")

    pubsub = fake_valkey.pubsub()
    await pubsub.subscribe("task_events")
    await pubsub.get_message(ignore_subscribe_messages=True, timeout=1.0)

    await client.patch(
        f"/api/tasks/{task['id']}", json={"output": "Container output"}
    )

    msg = await pubsub.get_message(ignore_subscribe_messages=True, timeout=1.0)
    assert msg is not None
    data = json.loads(msg["data"])
    assert data["event"] == "task_updated"
    assert data["task"]["output"] == "Container output"

    await pubsub.unsubscribe("task_events")
    await pubsub.aclose()


async def test_create_task_response_includes_runner_logs(client: AsyncClient):
    """Task response includes the runner_logs field (defaults to null)."""
    task = await create_task(client, "Quick task")
    assert "runner_logs" in task
    assert task["runner_logs"] is None


async def test_runner_logs_not_writable_via_patch(client: AsyncClient):
    """PATCH with runner_logs field is ignored (read-only)."""
    task = await create_task(client, "Quick task")
    resp = await client.patch(
        f"/api/tasks/{task['id']}", json={"runner_logs": "injected logs"}
    )
    assert resp.status_code == 200
    assert resp.json()["runner_logs"] is None


async def test_websocket_event_contains_all_task_response_fields(client: AsyncClient, fake_valkey):
    """WebSocket task_updated event payload must contain all TaskResponse fields.

    Regression test: ensures the event payload matches the API schema so the
    frontend never receives partial data that overwrites existing fields.
    """
    from main import TaskResponse

    task = await create_task(client, "Schema test task")

    pubsub = fake_valkey.pubsub()
    await pubsub.subscribe("task_events")
    await pubsub.get_message(ignore_subscribe_messages=True, timeout=1.0)

    await client.patch(
        f"/api/tasks/{task['id']}", json={"status": "pending"}
    )

    msg = await pubsub.get_message(ignore_subscribe_messages=True, timeout=1.0)
    assert msg is not None
    data = json.loads(msg["data"])
    assert data["event"] == "task_updated"

    expected_keys = set(TaskResponse.model_fields.keys())
    actual_keys = set(data["task"].keys())
    assert actual_keys == expected_keys, (
        f"WebSocket event payload key mismatch with TaskResponse.\n"
        f"Missing: {expected_keys - actual_keys}\n"
        f"Extra: {actual_keys - expected_keys}"
    )

    await pubsub.unsubscribe("task_events")
    await pubsub.aclose()
