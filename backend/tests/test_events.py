import json

from fakeredis.aioredis import FakeRedis
from httpx import AsyncClient

from events import CHANNEL


async def _subscribe(fake_valkey: FakeRedis):
    """Helper: subscribe to task_events and return the pubsub object."""
    pubsub = fake_valkey.pubsub()
    await pubsub.subscribe(CHANNEL)
    # Consume the subscribe confirmation message
    await pubsub.get_message(ignore_subscribe_messages=True, timeout=1.0)
    return pubsub


# --- POST /api/tasks publishes task_created ---


async def test_create_task_publishes_event(client: AsyncClient, fake_valkey: FakeRedis):
    pubsub = await _subscribe(fake_valkey)

    resp = await client.post("/api/tasks", json={"input": "Event test"})
    assert resp.status_code == 201
    task = resp.json()

    msg = await pubsub.get_message(ignore_subscribe_messages=True, timeout=1.0)
    assert msg is not None
    payload = json.loads(msg["data"])
    assert payload["event"] == "task_created"
    assert payload["task"]["id"] == task["id"]
    assert payload["task"]["title"] == "Event test"
    assert payload["task"]["status"] == "new"

    await pubsub.unsubscribe(CHANNEL)
    await pubsub.aclose()


# --- PATCH /api/tasks/{id} publishes task_updated ---


async def test_update_task_publishes_event(client: AsyncClient, fake_valkey: FakeRedis):
    resp = await client.post("/api/tasks", json={"input": "To update"})
    task_id = resp.json()["id"]

    pubsub = await _subscribe(fake_valkey)

    resp = await client.patch(f"/api/tasks/{task_id}", json={"status": "scheduled"})
    assert resp.status_code == 200

    msg = await pubsub.get_message(ignore_subscribe_messages=True, timeout=1.0)
    assert msg is not None
    payload = json.loads(msg["data"])
    assert payload["event"] == "task_updated"
    assert payload["task"]["id"] == task_id
    assert payload["task"]["status"] == "scheduled"

    await pubsub.unsubscribe(CHANNEL)
    await pubsub.aclose()


# --- No event on validation failure ---


async def test_no_event_on_create_validation_failure(client: AsyncClient, fake_valkey: FakeRedis):
    pubsub = await _subscribe(fake_valkey)

    resp = await client.post("/api/tasks", json={"input": ""})
    assert resp.status_code == 422

    msg = await pubsub.get_message(ignore_subscribe_messages=True, timeout=0.5)
    assert msg is None

    await pubsub.unsubscribe(CHANNEL)
    await pubsub.aclose()


async def test_no_event_on_update_not_found(client: AsyncClient, fake_valkey: FakeRedis):
    pubsub = await _subscribe(fake_valkey)

    resp = await client.patch(
        "/api/tasks/00000000-0000-0000-0000-000000000000",
        json={"title": "Nope"},
    )
    assert resp.status_code == 404

    msg = await pubsub.get_message(ignore_subscribe_messages=True, timeout=0.5)
    assert msg is None

    await pubsub.unsubscribe(CHANNEL)
    await pubsub.aclose()


async def test_no_event_on_update_invalid_status(client: AsyncClient, fake_valkey: FakeRedis):
    resp = await client.post("/api/tasks", json={"input": "For invalid status"})
    task_id = resp.json()["id"]

    pubsub = await _subscribe(fake_valkey)

    resp = await client.patch(f"/api/tasks/{task_id}", json={"status": "invalid"})
    assert resp.status_code == 422

    msg = await pubsub.get_message(ignore_subscribe_messages=True, timeout=0.5)
    assert msg is None

    await pubsub.unsubscribe(CHANNEL)
    await pubsub.aclose()
