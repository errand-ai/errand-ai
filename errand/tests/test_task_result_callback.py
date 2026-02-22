"""Tests for POST /api/internal/task-result/{task_id} callback endpoint."""
import secrets

import pytest
from fakeredis.aioredis import FakeRedis
from httpx import ASGITransport, AsyncClient

import events as events_module
from main import app


@pytest.fixture()
async def valkey():
    redis = FakeRedis(decode_responses=True)
    events_module._valkey = redis
    yield redis
    events_module._valkey = None
    await redis.aclose()


@pytest.fixture()
async def client(valkey):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()


TASK_ID = "test-task-123"
TOKEN = secrets.token_hex(32)
RESULT_BODY = '{"status":"completed","result":"done","questions":[]}'


async def test_valid_token_stores_result(client: AsyncClient, valkey: FakeRedis):
    await valkey.set(f"task_result_token:{TASK_ID}", TOKEN, ex=1800)

    resp = await client.post(
        f"/api/internal/task-result/{TASK_ID}",
        content=RESULT_BODY,
        headers={"Authorization": f"Bearer {TOKEN}", "Content-Type": "application/json"},
    )

    assert resp.status_code == 200
    assert resp.json() == {"ok": True}
    stored = await valkey.get(f"task_result:{TASK_ID}")
    assert stored == RESULT_BODY
    # Token consumed
    assert await valkey.get(f"task_result_token:{TASK_ID}") is None


async def test_invalid_token_returns_401(client: AsyncClient, valkey: FakeRedis):
    await valkey.set(f"task_result_token:{TASK_ID}", TOKEN, ex=1800)

    resp = await client.post(
        f"/api/internal/task-result/{TASK_ID}",
        content=RESULT_BODY,
        headers={"Authorization": "Bearer wrong-token", "Content-Type": "application/json"},
    )

    assert resp.status_code == 401
    assert await valkey.get(f"task_result:{TASK_ID}") is None


async def test_missing_auth_header_returns_401(client: AsyncClient, valkey: FakeRedis):
    await valkey.set(f"task_result_token:{TASK_ID}", TOKEN, ex=1800)

    resp = await client.post(
        f"/api/internal/task-result/{TASK_ID}",
        content=RESULT_BODY,
    )

    assert resp.status_code == 401


async def test_expired_token_returns_401(client: AsyncClient, valkey: FakeRedis):
    # No token stored in Valkey (simulates expiry)
    resp = await client.post(
        f"/api/internal/task-result/{TASK_ID}",
        content=RESULT_BODY,
        headers={"Authorization": f"Bearer {TOKEN}", "Content-Type": "application/json"},
    )

    assert resp.status_code == 401


async def test_token_consumed_after_single_use(client: AsyncClient, valkey: FakeRedis):
    await valkey.set(f"task_result_token:{TASK_ID}", TOKEN, ex=1800)

    resp1 = await client.post(
        f"/api/internal/task-result/{TASK_ID}",
        content=RESULT_BODY,
        headers={"Authorization": f"Bearer {TOKEN}", "Content-Type": "application/json"},
    )
    assert resp1.status_code == 200

    resp2 = await client.post(
        f"/api/internal/task-result/{TASK_ID}",
        content=RESULT_BODY,
        headers={"Authorization": f"Bearer {TOKEN}", "Content-Type": "application/json"},
    )
    assert resp2.status_code == 401


async def test_valkey_unavailable_returns_503(client: AsyncClient):
    # Set valkey to None to simulate unavailability
    events_module._valkey = None

    resp = await client.post(
        f"/api/internal/task-result/{TASK_ID}",
        content=RESULT_BODY,
        headers={"Authorization": f"Bearer {TOKEN}", "Content-Type": "application/json"},
    )

    assert resp.status_code == 503
