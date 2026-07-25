"""Tests for the eval-framework MCP tools (clone/delete profile, search_tasks,
start/record/finish/get eval run). Covers mcp-profile-tools, mcp-task-search,
and eval-results-recording specs.
"""

import json
import uuid
from datetime import datetime, timezone

import pytest
from sqlalchemy import select

import version_checker
from models import Task, TaskProfile

pytestmark = pytest.mark.anyio


async def _add_profile(session_factory, name, model=None):
    async with session_factory() as session:
        p = TaskProfile(name=name, model=model or {"provider_id": None, "model": "base-model"},
                        system_prompt="sp", max_turns=20)
        session.add(p)
        await session.commit()
        await session.refresh(p)
        return p.id


async def _add_task(session_factory, *, status="completed", is_eval=False, title="t",
                    profile_id=None, created_at=None, runner_logs=None, retry_count=0):
    async with session_factory() as session:
        t = Task(title=title, status=status, is_eval=is_eval, profile_id=profile_id,
                 runner_logs=runner_logs, retry_count=retry_count, position=0)
        if created_at is not None:
            t.created_at = created_at
        session.add(t)
        await session.commit()
        await session.refresh(t)
        return t.id


# --- clone_task_profile -----------------------------------------------------

async def test_clone_requires_eval_prefix(db_session):
    _, sf = db_session
    await _add_profile(sf, "job-research")
    from mcp_server import clone_task_profile
    res = json.loads(await clone_task_profile("job-research", "job-research-v2"))
    assert "error" in res and "eval--" in res["error"]
    async with sf() as session:
        assert (await session.execute(select(TaskProfile).where(TaskProfile.name == "job-research-v2"))).scalar_one_or_none() is None


async def test_clone_copies_fields_and_overrides_model(db_session):
    _, sf = db_session
    await _add_profile(sf, "job-research", model={"provider_id": "p1", "model": "old"})
    from mcp_server import clone_task_profile
    res = json.loads(await clone_task_profile("job-research", "eval--job-research--gemma4", model="gemma4-27b"))
    assert res["ok"] and res["reused"] is False
    async with sf() as session:
        clone = (await session.execute(select(TaskProfile).where(TaskProfile.name == "eval--job-research--gemma4"))).scalar_one()
        assert clone.system_prompt == "sp"  # copied
        assert clone.model == {"provider_id": "p1", "model": "gemma4-27b"}  # provider kept, slug overridden


async def test_clone_nonexistent_source(db_session):
    _, sf = db_session
    from mcp_server import clone_task_profile
    res = json.loads(await clone_task_profile("nope", "eval--x--y"))
    assert "error" in res and "not found" in res["error"]


async def test_clone_idempotent_reuse(db_session):
    _, sf = db_session
    await _add_profile(sf, "job-research")
    from mcp_server import clone_task_profile
    first = json.loads(await clone_task_profile("job-research", "eval--job-research--gemma4", max_turns=5))
    second = json.loads(await clone_task_profile("job-research", "eval--job-research--gemma4", max_turns=99))
    assert second["reused"] is True
    assert second["profile"]["id"] == first["profile"]["id"]
    assert second["profile"]["max_turns"] == 5  # unmodified


# --- delete_task_profile ----------------------------------------------------

async def test_delete_requires_eval_prefix(db_session):
    _, sf = db_session
    await _add_profile(sf, "email-triage")
    from mcp_server import delete_task_profile
    res = json.loads(await delete_task_profile("email-triage"))
    assert "error" in res
    async with sf() as session:
        assert (await session.execute(select(TaskProfile).where(TaskProfile.name == "email-triage"))).scalar_one_or_none() is not None


async def test_delete_eval_profile_and_idempotent(db_session):
    _, sf = db_session
    await _add_profile(sf, "eval--job-research--gemma4")
    from mcp_server import delete_task_profile
    assert json.loads(await delete_task_profile("eval--job-research--gemma4"))["deleted"] is True
    # second delete: idempotent success
    assert json.loads(await delete_task_profile("eval--job-research--gemma4"))["deleted"] is False


# --- search_tasks -----------------------------------------------------------

async def test_search_by_profile_and_status(db_session):
    _, sf = db_session
    pid = await _add_profile(sf, "job-research")
    await _add_task(sf, status="archived", profile_id=pid, title="jr-arch", runner_logs="{}")
    await _add_task(sf, status="completed", profile_id=pid, title="jr-done")
    from mcp_server import search_tasks
    rows = json.loads(await search_tasks(profile="job-research", status="archived"))
    assert [r["title"] for r in rows] == ["jr-arch"]
    assert rows[0]["profile_name"] == "job-research" and rows[0]["has_logs"] is True


async def test_search_full_history_and_date_range(db_session):
    _, sf = db_session
    march = datetime(2026, 3, 15, tzinfo=timezone.utc)
    april = datetime(2026, 4, 15, tzinfo=timezone.utc)
    await _add_task(sf, status="archived", title="march", created_at=march)
    await _add_task(sf, status="archived", title="april", created_at=april)
    from mcp_server import search_tasks
    rows = json.loads(await search_tasks(created_after="2026-03-01T00:00:00Z", created_before="2026-04-01T00:00:00Z"))
    assert [r["title"] for r in rows] == ["march"]
    # Offset-less (naive) bounds are treated as UTC, not rejected or mis-compared.
    naive = json.loads(await search_tasks(created_after="2026-03-01T00:00:00", created_before="2026-04-01T00:00:00"))
    assert [r["title"] for r in naive] == ["march"]


async def test_search_limit_applied_and_capped(db_session):
    _, sf = db_session
    for i in range(5):
        await _add_task(sf, status="completed", title=f"t{i}")
    from mcp_server import search_tasks
    # limit is honoured...
    assert len(json.loads(await search_tasks(limit=2))) == 2
    # ...and an over-large limit is capped (never errors, returns all available).
    assert len(json.loads(await search_tasks(limit=1000))) == 5


async def test_search_excludes_evals_by_default(db_session):
    _, sf = db_session
    await _add_task(sf, status="completed", title="prod", is_eval=False)
    await _add_task(sf, status="completed", title="eval", is_eval=True)
    from mcp_server import search_tasks
    default = {r["title"] for r in json.loads(await search_tasks())}
    assert "prod" in default and "eval" not in default
    only_eval = {r["title"] for r in json.loads(await search_tasks(is_eval=True))}
    assert only_eval == {"eval"}
    only_prod = {r["title"] for r in json.loads(await search_tasks(is_eval=False))}
    assert only_prod == {"prod"}


# --- eval run lifecycle -----------------------------------------------------

async def test_start_eval_run_stamps_version(db_session):
    from mcp_server import start_eval_run
    res = json.loads(await start_eval_run(mode="live", corpus_version="abc1234", judge_model="claude-opus-4-8"))
    assert res["ok"] and len(res["run_id"]) == 36
    assert res["errand_version"] == version_checker.APP_VERSION


async def test_start_eval_run_invalid_mode(db_session):
    from mcp_server import start_eval_run
    res = json.loads(await start_eval_run(mode="dryrun", corpus_version="x", judge_model="j"))
    assert "error" in res


async def test_record_result_and_duplicate_rejected(db_session):
    from mcp_server import start_eval_run, record_eval_result
    run_id = json.loads(await start_eval_run(mode="live", corpus_version="v", judge_model="j"))["run_id"]
    ok = json.loads(await record_eval_result(run_id, "job-research/001", "gemma4", 2, "pass", score=8.0))
    assert ok["ok"] and len(ok["result_id"]) == 36
    dup = json.loads(await record_eval_result(run_id, "job-research/001", "gemma4", 2, "fail"))
    assert "error" in dup and "duplicate" in dup["error"]


async def test_record_invalid_verdict_and_unknown_run(db_session):
    from mcp_server import start_eval_run, record_eval_result
    run_id = json.loads(await start_eval_run(mode="live", corpus_version="v", judge_model="j"))["run_id"]
    assert "error" in json.loads(await record_eval_result(run_id, "w", "m", 0, "maybe"))
    assert "error" in json.loads(await record_eval_result(str(uuid.uuid4()), "w", "m", 0, "pass"))


async def test_finish_run_rejects_further_records(db_session):
    from mcp_server import start_eval_run, record_eval_result, finish_eval_run
    run_id = json.loads(await start_eval_run(mode="live", corpus_version="v", judge_model="j"))["run_id"]
    assert json.loads(await finish_eval_run(run_id))["ok"]
    assert "error" in json.loads(await finish_eval_run(run_id))  # double-finish
    rejected = json.loads(await record_eval_result(run_id, "w", "m", 0, "pass"))
    assert "error" in rejected and "finished" in rejected["error"]


async def test_get_eval_run_lists_results(db_session):
    from mcp_server import start_eval_run, record_eval_result, get_eval_run
    run_id = json.loads(await start_eval_run(mode="retro", corpus_version="v", judge_model="j"))["run_id"]
    await record_eval_result(run_id, "job-research", "gemma4", 0, "pass", score=7.5)
    await record_eval_result(run_id, "job-research", "gemma4", 1, "fail", score=2.0)
    run = json.loads(await get_eval_run(run_id))
    assert run["mode"] == "retro" and len(run["results"]) == 2
    verdicts = {(r["rep"], r["verdict"]) for r in run["results"]}
    assert verdicts == {(0, "pass"), (1, "fail")}
