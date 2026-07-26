"""Tests for the live run loop and retro mode using a fake MCP client.

Covers eval-driver: sequential-per-model batching, single in-flight task, profile
lifecycle, resumability, infra retry-once; and retro model attribution + skips.
"""

import json

import pytest

import corpus as corpus_mod
import retro as retro_mod
import runner as runner_mod

pytestmark = pytest.mark.anyio


def _task(workload="job-research", reps=2, timeout=10, assertions=None):
    return corpus_mod.CorpusTask(
        id=f"{workload}/001", workload=workload, base_profile=workload,
        description="do the thing", rubric="be good", assertions=assertions or [],
        reps=reps, timeout_minutes=timeout, path="x",
    )


class Cfg:
    judge_model = "claude-opus-4-8"
    digest_max_chars = 12000
    yield_poll_interval_seconds = 0
    task_poll_interval_seconds = 0

    def __init__(self, models):
        self.models = models


def _judgeable_logs(model="m", tool="web_search"):
    return "\n".join(json.dumps(e) for e in [
        {"type": "agent_start", "data": {}},
        {"type": "llm_turn_start", "data": {"model": model, "turn_id": 1}},
        {"type": "tool_call", "data": {"tool": tool, "args": {}}},
        {"type": "agent_end", "data": {"output": {"result": "answer"}}},
    ])


def _infra_logs():
    return json.dumps({"type": "error", "data": {"message": "Could not install requirements.txt"}})


class FakeClient:
    """Records calls and returns scripted responses for the driver's tool calls."""

    def __init__(self, existing_results=None, logs_script=None, list_tasks_script=None):
        self.calls = []
        self.recorded = []
        self.created_profiles = []
        self.deleted_profiles = []
        self.finished = False
        self._existing = {"results": existing_results or []}
        self._logs_script = list(logs_script or [])
        self._list_tasks_script = list(list_tasks_script or [])
        self._task_seq = 0

    async def get_eval_run(self, run_id):
        return self._existing

    async def list_tasks(self, status=None):
        if self._list_tasks_script:
            return self._list_tasks_script.pop(0)
        return []

    async def clone_task_profile(self, source_profile, new_name, model=None, **kw):
        self.created_profiles.append(new_name)
        return {"ok": True, "reused": False, "profile": {"name": new_name}}

    async def delete_task_profile(self, name):
        self.deleted_profiles.append(name)
        return {"ok": True, "deleted": True}

    async def new_task(self, description, profile=None, title=None):
        self._task_seq += 1
        self.calls.append(("new_task", profile))
        return f"00000000-0000-0000-0000-{self._task_seq:012d}"

    async def task_status(self, task_id, fmt="json"):
        return {"status": "completed"}

    async def task_logs(self, task_id):
        return self._logs_script.pop(0) if self._logs_script else _judgeable_logs()

    async def task_output(self, task_id):
        return "answer"

    async def record_eval_result(self, **fields):
        self.recorded.append(fields)
        return {"ok": True, "result_id": "r"}

    async def finish_eval_run(self, run_id, notes=None):
        self.finished = True
        return {"ok": True}

    async def search_tasks(self, **filters):
        return []


def _fake_judge(prompt, model):
    return json.dumps({"pass": True, "score": 8, "reasons": []})


async def test_sequential_per_model_and_cleanup():
    client = FakeClient()
    cfg = Cfg(models=["gemma4", "qwen36"])
    tasks = [_task(reps=2)]
    await runner_mod.run_matrix(client, cfg, tasks, "run1", no_yield=True, sleep=_nosleep, run_claude=_fake_judge)

    # All gemma4 cells recorded before any qwen36 cell.
    models_in_order = [r["model"] for r in client.recorded]
    assert models_in_order == ["gemma4", "gemma4", "qwen36", "qwen36"]
    # Profiles created per (workload, model) and cleaned up at the end.
    assert set(client.created_profiles) == {"eval--job-research--gemma4", "eval--job-research--qwen36"}
    assert set(client.deleted_profiles) == set(client.created_profiles)
    assert client.finished is True


async def test_resumability_skips_recorded_cells():
    existing = [{"workload": "job-research", "model": "gemma4", "rep": 0, "verdict": "pass"}]
    client = FakeClient(existing_results=existing)
    cfg = Cfg(models=["gemma4"])
    await runner_mod.run_matrix(client, cfg, [_task(reps=2)], "run1", no_yield=True, sleep=_nosleep, run_claude=_fake_judge)
    # rep 0 already recorded → only rep 1 executed.
    assert [r["rep"] for r in client.recorded] == [1]


async def test_infra_failure_retried_once_then_recovers():
    # First submission infra-fails, retry is judgeable → scored, no infra verdict.
    client = FakeClient(logs_script=[_infra_logs(), _judgeable_logs()])
    cfg = Cfg(models=["gemma4"])
    await runner_mod.run_matrix(client, cfg, [_task(reps=1)], "run1", no_yield=True, sleep=_nosleep, run_claude=_fake_judge)
    assert len(client.recorded) == 1
    assert client.recorded[0]["verdict"] == "pass"  # recovered, not infra_failure


async def test_persistent_infra_failure_recorded():
    client = FakeClient(logs_script=[_infra_logs(), _infra_logs()])
    cfg = Cfg(models=["gemma4"])
    await runner_mod.run_matrix(client, cfg, [_task(reps=1)], "run1", no_yield=True, sleep=_nosleep, run_claude=_fake_judge)
    assert client.recorded[0]["verdict"] == "infra_failure"


async def test_yield_waits_for_production():
    # search_tasks(is_eval=False, status=pending) returns a task on the first
    # check (busy), then nothing (clear). The driver waits, then submits.
    calls = {"sleep": 0}

    async def sleep(_):
        calls["sleep"] += 1

    class YieldClient(FakeClient):
        def __init__(self):
            super().__init__()
            self._busy_checks = 1  # report busy once, then clear

        async def search_tasks(self, **filters):
            if filters.get("status") == "pending" and self._busy_checks > 0:
                self._busy_checks -= 1
                return [{"id": "prod1", "status": "pending"}]
            return []

    client = YieldClient()
    await runner_mod.run_matrix(client, Cfg(models=["gemma4"]), [_task(reps=1)],
                                "run1", no_yield=False, sleep=sleep, run_claude=_fake_judge)
    assert calls["sleep"] >= 1  # yielded at least once
    assert len(client.recorded) == 1


async def test_reused_profiles_are_not_deleted():
    # A pre-existing (reused) eval profile must not be deleted at run end — only
    # profiles the driver created are cleaned up.
    class ReuseClient(FakeClient):
        async def clone_task_profile(self, source_profile, new_name, model=None, **kw):
            self.created_profiles.append(new_name)
            return {"ok": True, "reused": True, "profile": {"name": new_name}}

    client = ReuseClient()
    await runner_mod.run_matrix(client, Cfg(models=["gemma4"]), [_task(reps=1)],
                                "run1", no_yield=True, sleep=_nosleep, run_claude=_fake_judge)
    assert client.deleted_profiles == []  # reused profile left in place
    assert len(client.recorded) == 1


async def test_non_dict_status_keeps_polling_then_terminal():
    # A transient non-dict task_status (e.g. an error string) must NOT be treated
    # as terminal; the driver keeps polling until a real terminal status.
    class FlakyStatusClient(FakeClient):
        def __init__(self):
            super().__init__()
            self._status_calls = 0

        async def task_status(self, task_id, fmt="json"):
            self._status_calls += 1
            return "Error: transient" if self._status_calls == 1 else {"status": "completed"}

    client = FlakyStatusClient()
    await runner_mod.run_matrix(client, Cfg(models=["gemma4"]), [_task(reps=1)],
                                "run1", no_yield=True, sleep=_nosleep, run_claude=_fake_judge)
    assert client._status_calls >= 2  # polled past the transient error
    assert client.recorded[0]["verdict"] == "pass"


async def test_retro_attributes_model_and_skips_unusable():
    class RetroClient(FakeClient):
        async def search_tasks(self, **filters):
            return [{"id": "t1", "title": "job research A"},
                    {"id": "t2", "title": "job research B"},
                    {"id": "t3", "title": "job research C"}]

        async def task_logs(self, task_id):
            return {
                "t1": _judgeable_logs(model="gemma-3-27b"),
                "t2": json.dumps({"type": "agent_start", "data": {}}),  # no llm_turn_start → no model
                "t3": _judgeable_logs(model="qwen3-30b"),
            }[task_id]

    client = RetroClient()
    cfg = Cfg(models=[])
    summary = await retro_mod.run_retro(client, cfg, "job-research", sample=5, run_id="retro1",
                                        rubric="be good", run_claude=_fake_judge)
    # t2 skipped (no model); t1 & t3 recorded with attributed models.
    assert summary["recorded"] == 2
    assert {r["model"] for r in client.recorded} == {"gemma-3-27b", "qwen3-30b"}
    assert all(r["rep"] == 0 for r in client.recorded)
    assert len(summary["skipped"]) == 1 and summary["skipped"][0]["reason"] == "no_model_in_transcript"


async def test_retro_skips_no_output_tasks():
    class RetroClient(FakeClient):
        async def search_tasks(self, **filters):
            return [{"id": "t1", "title": "A"}, {"id": "t2", "title": "B"}]

        async def task_logs(self, task_id):
            return _judgeable_logs(model="gemma-3-27b")

        async def task_output(self, task_id):
            return "" if task_id == "t2" else "a real answer"

    client = RetroClient()
    summary = await retro_mod.run_retro(client, Cfg(models=[]), "job-research", sample=5,
                                        run_id="retro1", rubric="be good", run_claude=_fake_judge)
    # t2 has no output → skipped, not recorded as a failure.
    assert summary["recorded"] == 1
    assert [s["reason"] for s in summary["skipped"]] == ["no_output"]
    assert len(client.recorded) == 1


async def _nosleep(_seconds):
    return None
