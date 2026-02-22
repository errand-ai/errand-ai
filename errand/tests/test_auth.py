from httpx import AsyncClient


async def test_unauthenticated_get_tasks_rejected(unauth_client: AsyncClient):
    resp = await unauth_client.get("/api/tasks")
    assert resp.status_code in (401, 403)


async def test_unauthenticated_post_tasks_rejected(unauth_client: AsyncClient):
    resp = await unauth_client.post("/api/tasks", json={"title": "Should fail"})
    assert resp.status_code in (401, 403)
