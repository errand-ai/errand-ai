from httpx import AsyncClient


async def create_task_with_status(client: AsyncClient, title: str, status: str) -> dict:
    resp = await client.post("/api/tasks", json={"input": title})
    assert resp.status_code == 201
    task = resp.json()
    if status != "review":
        resp = await client.patch(f"/api/tasks/{task['id']}", json={"status": status})
        assert resp.status_code == 200
        task = resp.json()
    return task


async def test_queue_depth_with_pending_tasks(client: AsyncClient):
    for i in range(5):
        await create_task_with_status(client, f"Task {i}", "pending")
    # Also add a non-pending task to verify it's not counted
    await create_task_with_status(client, "Running task", "running")

    resp = await client.get("/metrics/queue")
    assert resp.status_code == 200
    assert resp.json() == {"queue_depth": 5}


async def test_queue_depth_zero(client: AsyncClient):
    # Create a task that is NOT pending
    await create_task_with_status(client, "Review task", "review")

    resp = await client.get("/metrics/queue")
    assert resp.status_code == 200
    assert resp.json() == {"queue_depth": 0}


async def test_metrics_no_auth_required(unauth_client: AsyncClient):
    resp = await unauth_client.get("/metrics/queue")
    assert resp.status_code == 200
    assert resp.json() == {"queue_depth": 0}
