"""Tests for eval-task marking (is_eval) and board exclusion.

Covers task-api spec: is_eval set server-side for eval-- profiles, survives
profile deletion, and GET /api/tasks[/archived] exclude eval tasks by default.
"""

import uuid

import pytest
from sqlalchemy import select

from models import Task, TaskProfile
import eval_marking

pytestmark = pytest.mark.anyio


async def _add_profile(session_factory, name: str) -> uuid.UUID:
    async with session_factory() as session:
        p = TaskProfile(name=name, model={"provider": "openai", "name": "gpt-4o"})
        session.add(p)
        await session.commit()
        await session.refresh(p)
        return p.id


async def _add_task(session_factory, *, status: str, is_eval: bool, profile_id=None, title="t"):
    async with session_factory() as session:
        t = Task(title=title, status=status, is_eval=is_eval, profile_id=profile_id, position=0)
        session.add(t)
        await session.commit()
        await session.refresh(t)
        return t.id


def test_is_eval_profile_name():
    assert eval_marking.is_eval_profile_name("eval--job-research--gemma4") is True
    assert eval_marking.is_eval_profile_name("job-research") is False
    assert eval_marking.is_eval_profile_name(None) is False
    assert eval_marking.is_eval_profile_name("") is False


async def test_new_task_under_eval_profile_flagged(db_session):
    _, session_factory = db_session
    await _add_profile(session_factory, "eval--job-research--gemma4")

    from mcp_server import new_task
    task_uuid = await new_task("Run the job research workload", profile="eval--job-research--gemma4", title="Eval")

    async with session_factory() as session:
        task = (await session.execute(select(Task).where(Task.id == uuid.UUID(task_uuid)))).scalar_one()
        assert task.is_eval is True


async def test_new_task_under_normal_profile_not_flagged(db_session):
    _, session_factory = db_session
    await _add_profile(session_factory, "job-research")

    from mcp_server import new_task
    task_uuid = await new_task("Run the job research workload", profile="job-research", title="Prod")

    async with session_factory() as session:
        task = (await session.execute(select(Task).where(Task.id == uuid.UUID(task_uuid)))).scalar_one()
        assert task.is_eval is False


async def test_new_task_without_profile_not_flagged(db_session):
    _, session_factory = db_session
    from mcp_server import new_task
    task_uuid = await new_task("Fix bug", title="t")
    async with session_factory() as session:
        task = (await session.execute(select(Task).where(Task.id == uuid.UUID(task_uuid)))).scalar_one()
        assert task.is_eval is False


async def test_flag_survives_profile_dissociation(db_session):
    # is_eval is a persisted column, not derived from the (live) profile — so it
    # survives the profile being deleted (profile_id set null by ON DELETE SET
    # NULL in Postgres). SQLite tests don't enforce FK actions, so we simulate the
    # dissociation directly; the invariant under test is that the flag persists.
    _, session_factory = db_session
    pid = await _add_profile(session_factory, "eval--job-research--gemma4")
    tid = await _add_task(session_factory, status="pending", is_eval=True, profile_id=pid)

    async with session_factory() as session:
        task = (await session.execute(select(Task).where(Task.id == tid))).scalar_one()
        task.profile_id = None  # what ON DELETE SET NULL does when the profile is deleted
        await session.commit()

    async with session_factory() as session:
        task = (await session.execute(select(Task).where(Task.id == tid))).scalar_one()
        assert task.profile_id is None
        assert task.is_eval is True


async def test_list_tasks_excludes_evals_by_default(db_session, admin_mcp_client):
    _, session_factory = db_session
    await _add_task(session_factory, status="pending", is_eval=False, title="prod")
    await _add_task(session_factory, status="pending", is_eval=True, title="eval")

    resp = await admin_mcp_client.get("/api/tasks")
    assert resp.status_code == 200
    titles = {t["title"] for t in resp.json()}
    assert "prod" in titles and "eval" not in titles
    # is_eval surfaced in the response schema.
    assert all(t["is_eval"] is False for t in resp.json())

    resp = await admin_mcp_client.get("/api/tasks?include_evals=true")
    titles = {t["title"] for t in resp.json()}
    assert {"prod", "eval"} <= titles


async def test_archived_excludes_evals_by_default(db_session, admin_mcp_client):
    _, session_factory = db_session
    await _add_task(session_factory, status="archived", is_eval=False, title="prod-arch")
    await _add_task(session_factory, status="archived", is_eval=True, title="eval-arch")

    resp = await admin_mcp_client.get("/api/tasks/archived")
    assert resp.status_code == 200
    titles = {t["title"] for t in resp.json()}
    assert "prod-arch" in titles and "eval-arch" not in titles

    resp = await admin_mcp_client.get("/api/tasks/archived?include_evals=true")
    titles = {t["title"] for t in resp.json()}
    assert {"prod-arch", "eval-arch"} <= titles
