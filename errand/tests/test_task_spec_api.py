"""`/api/task-specs` — the intake clarification API."""
from unittest.mock import AsyncMock, patch

from httpx import AsyncClient

from llm import LLMResult
from main import app, require_editor

QUESTIONS = [
    {"id": "source", "text": "Which spreadsheet holds the numbers?", "kind": "free_text"},
    {"id": "channel", "text": "Where should they go?", "kind": "choice", "choices": ["Email", "Slack"]},
]

ASKING = LLMResult(title="Quarterly Numbers", success=True, description="Send the quarterly numbers", questions=QUESTIONS)
READY = LLMResult(
    title="Quarterly Numbers",
    success=True,
    description="Email the Q3 finance sheet numbers to me",
)


def _classifier(*results):
    return patch("clarify.generate_title", AsyncMock(side_effect=list(results)))


async def test_full_loop_start_answer_confirm(client: AsyncClient):
    with _classifier(ASKING, READY):
        started = await client.post("/api/task-specs", json={"input": "Send me the quarterly numbers"})
        assert started.status_code == 201
        draft = started.json()
        assert draft["status"] == "drafting"
        assert draft["questions"] == QUESTIONS
        assert draft["max_rounds"] == 2
        assert (await client.get("/api/tasks")).json() == []

        answered = await client.post(
            f"/api/task-specs/{draft['id']}/answer",
            json={"responses": {"source": "Q3 finance", "channel": "Email"}},
        )
        assert answered.status_code == 200
        assert answered.json()["status"] == "ready"
        assert answered.json()["round"] == 1

    listed = await client.get("/api/task-specs")
    assert [d["id"] for d in listed.json()] == [draft["id"]]

    confirmed = await client.post(f"/api/task-specs/{draft['id']}/confirm")
    assert confirmed.status_code == 201
    task = confirmed.json()
    assert task["title"] == "Quarterly Numbers"
    assert task["description"] == "Email the Q3 finance sheet numbers to me"
    assert task["status"] == "pending"
    assert task["created_by"] == "test@example.com"
    assert "Needs Info" not in task["tags"]

    tasks = (await client.get("/api/tasks")).json()
    assert [t["id"] for t in tasks] == [task["id"]]

    fetched = (await client.get(f"/api/task-specs/{draft['id']}")).json()
    assert fetched["status"] == "confirmed"
    assert fetched["resolved_task_id"] == task["id"]
    assert (await client.get("/api/task-specs")).json() == []

    again = await client.post(f"/api/task-specs/{draft['id']}/confirm")
    assert again.status_code == 409
    assert len((await client.get("/api/tasks")).json()) == 1


async def test_start_ready_payload(client: AsyncClient):
    with _classifier(READY):
        resp = await client.post("/api/task-specs", json={"input": "Email me the Q3 numbers"})
    body = resp.json()
    assert body["status"] == "ready"
    assert body["questions"] == []
    assert body["spec_preview"]["title"] == "Quarterly Numbers"


async def test_blank_input_rejected(client: AsyncClient):
    assert (await client.post("/api/task-specs", json={"input": "   "})).status_code == 422
    assert (await client.post("/api/task-specs", json={})).status_code == 422


async def test_unauthenticated_is_401(unauth_client: AsyncClient):
    resp = await unauth_client.post("/api/task-specs", json={"input": "anything"})
    assert resp.status_code == 401


async def test_viewer_is_forbidden(viewer_client: AsyncClient):
    resp = await viewer_client.post("/api/task-specs", json={"input": "anything"})
    assert resp.status_code == 403


async def test_other_user_gets_404(client: AsyncClient):
    with _classifier(ASKING):
        draft = (await client.post("/api/task-specs", json={"input": "Send me the quarterly numbers"})).json()

    app.dependency_overrides[require_editor] = lambda: {"sub": "b", "email": "bob@example.com", "_roles": ["editor"]}
    try:
        assert (await client.get(f"/api/task-specs/{draft['id']}")).status_code == 404
        answered = await client.post(f"/api/task-specs/{draft['id']}/answer", json={"responses": {"source": "x"}})
        assert answered.status_code == 404
        assert (await client.post(f"/api/task-specs/{draft['id']}/confirm")).status_code == 404
        assert (await client.post(f"/api/task-specs/{draft['id']}/cancel")).status_code == 404
        assert (await client.get("/api/task-specs")).json() == []
    finally:
        from tests.conftest import FAKE_USER_CLAIMS

        app.dependency_overrides[require_editor] = lambda: FAKE_USER_CLAIMS

    still = (await client.get(f"/api/task-specs/{draft['id']}")).json()
    assert still["status"] == "drafting"
    assert still["round"] == 0


async def test_unknown_and_malformed_ids_are_404(client: AsyncClient):
    assert (await client.get("/api/task-specs/00000000-0000-0000-0000-000000000000")).status_code == 404
    assert (await client.get("/api/task-specs/nope")).status_code == 404


async def test_cancel_then_answer_is_409(client: AsyncClient):
    with _classifier(ASKING):
        draft = (await client.post("/api/task-specs", json={"input": "Send me the quarterly numbers"})).json()
    cancelled = await client.post(f"/api/task-specs/{draft['id']}/cancel")
    assert cancelled.json()["status"] == "abandoned"
    answered = await client.post(f"/api/task-specs/{draft['id']}/answer", json={"responses": {"source": "x"}})
    assert answered.status_code == 409


async def test_clarification_max_rounds_setting_validated(admin_client: AsyncClient):
    bad = await admin_client.put("/api/settings", json={"clarification_max_rounds": 0})
    assert bad.status_code == 422
    good = await admin_client.put("/api/settings", json={"clarification_max_rounds": 3})
    assert good.status_code == 200
