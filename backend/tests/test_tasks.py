import pytest
from httpx import AsyncClient

VALID_STATUSES = ["new", "scheduled", "pending", "running", "review", "completed"]


async def create_task(client: AsyncClient, input_text: str = "Test task") -> dict:
    resp = await client.post("/api/tasks", json={"input": input_text})
    assert resp.status_code == 201
    return resp.json()


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
    # Most recent first
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
    assert "Needs Info" in data["tags"]
    assert "id" in data
    assert "created_at" in data
    assert "updated_at" in data


async def test_create_task_missing_input(client: AsyncClient):
    resp = await client.post("/api/tasks", json={})
    assert resp.status_code == 422


async def test_create_task_empty_input(client: AsyncClient):
    resp = await client.post("/api/tasks", json={"input": ""})
    assert resp.status_code == 422


async def test_create_task_response_includes_description_and_tags(client: AsyncClient):
    """Every task response includes description and tags fields."""
    task = await create_task(client, "Quick task")
    assert "description" in task
    assert "tags" in task
    assert isinstance(task["tags"], list)


# --- GET /api/tasks/{id} ---


async def test_get_task_found(client: AsyncClient):
    task = await create_task(client, "Find me")
    resp = await client.get(f"/api/tasks/{task['id']}")
    assert resp.status_code == 200
    data = resp.json()
    assert data["title"] == "Find me"
    assert "description" in data
    assert "tags" in data


async def test_get_task_not_found(client: AsyncClient):
    resp = await client.get("/api/tasks/00000000-0000-0000-0000-000000000000")
    assert resp.status_code == 404


# --- PATCH /api/tasks/{id} ---


async def test_update_task_status(client: AsyncClient):
    task = await create_task(client)
    resp = await client.patch(f"/api/tasks/{task['id']}", json={"status": "scheduled"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "scheduled"
    assert data["updated_at"] >= task["updated_at"]


async def test_update_task_title(client: AsyncClient):
    task = await create_task(client)
    resp = await client.patch(f"/api/tasks/{task['id']}", json={"title": "New title"})
    assert resp.status_code == 200
    assert resp.json()["title"] == "New title"


async def test_update_task_both(client: AsyncClient):
    task = await create_task(client)
    resp = await client.patch(
        f"/api/tasks/{task['id']}", json={"title": "New title", "status": "review"}
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["title"] == "New title"
    assert data["status"] == "review"


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


async def test_update_task_description(client: AsyncClient):
    task = await create_task(client)
    resp = await client.patch(
        f"/api/tasks/{task['id']}", json={"description": "Some details here"}
    )
    assert resp.status_code == 200
    assert resp.json()["description"] == "Some details here"


# --- Valid status enforcement ---


@pytest.mark.parametrize("status", VALID_STATUSES)
async def test_all_valid_statuses_accepted(client: AsyncClient, status: str):
    task = await create_task(client)
    resp = await client.patch(f"/api/tasks/{task['id']}", json={"status": status})
    assert resp.status_code == 200
    assert resp.json()["status"] == status


async def test_invalid_status_failed_rejected(client: AsyncClient):
    task = await create_task(client)
    resp = await client.patch(f"/api/tasks/{task['id']}", json={"status": "failed"})
    assert resp.status_code == 422


async def test_need_input_status_rejected(client: AsyncClient):
    """need-input is no longer a valid status (replaced by tags)."""
    task = await create_task(client)
    resp = await client.patch(f"/api/tasks/{task['id']}", json={"status": "need-input"})
    assert resp.status_code == 422
