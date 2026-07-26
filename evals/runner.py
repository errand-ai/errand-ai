"""Live run loop: sequential-per-model matrix execution with one in-flight task.

For each model (strictly sequential) and each corpus task, the driver clones an
``eval--<workload>--<slug>`` profile, then runs each rep one at a time:
yield-to-production → submit → poll to terminal → fetch output+logs → classify →
score (or record infra) → record. Infra-failed reps are retried once. Cells with
an existing recorded result are skipped (resumability). Profiles the driver
created are deleted and the run is finished only on successful completion, so an
interrupted run leaves reusable profiles and an open run to resume.

Pure helpers here are unit-tested; the async loop takes an injected client,
clock, and sleep so it can be driven by a fake client in tests.
"""

from __future__ import annotations

import asyncio
import re
import time

import scoring as scoring_mod
import transcript as transcript_mod

# A submitted eval task is done only when it reaches one of these statuses. An
# unrecognised/absent status (e.g. a transient error payload from task_status) is
# treated as "still running" so we keep polling rather than prematurely proceed.
_TERMINAL_STATUSES = {"completed", "review", "needs_input", "archived", "deleted", "failed"}
# Production work the driver yields to (in-progress, not future-scheduled).
_ACTIVE_PRODUCTION = ("pending", "running")


def derive_slug(model: str) -> str:
    """Filesystem/name-safe short slug for a model, used in the profile name."""
    return re.sub(r"[^a-z0-9]+", "-", str(model).lower()).strip("-")


def eval_profile_name(workload: str, model: str) -> str:
    return f"eval--{workload}--{derive_slug(model)}"


def recorded_cells(run_response: dict | None) -> set[tuple[str, str, int]]:
    """The set of (workload, model, rep) cells already recorded for a run."""
    cells: set[tuple[str, str, int]] = set()
    for r in (run_response or {}).get("results", []) or []:
        cells.add((r["workload"], r["model"], r["rep"]))
    return cells


def is_terminal(status: str | None) -> bool:
    return status in _TERMINAL_STATUSES


def _task_id_from_new_task(resp) -> str | None:
    """new_task returns a bare UUID string on success, or an 'Error: ...' string."""
    if isinstance(resp, str) and not resp.startswith("Error"):
        return resp.strip()
    if isinstance(resp, dict):
        return resp.get("id")
    return None


async def production_busy(client) -> bool:
    """True if any active *non-eval* task is pending/running.

    Uses ``search_tasks(is_eval=False, ...)`` rather than ``list_tasks`` (which
    doesn't distinguish eval tasks), so the driver yields only to real production
    work, never to other eval tasks.
    """
    for status in _ACTIVE_PRODUCTION:
        rows = await client.search_tasks(is_eval=False, status=status, limit=1)
        if isinstance(rows, list) and rows:
            return True
    return False


async def _yield_to_production(client, interval: float, sleep) -> None:
    while await production_busy(client):
        await sleep(interval)


async def _submit_and_wait(client, description, profile, timeout_minutes, poll_interval, sleep, now):
    """Submit one eval task and poll to a terminal state or timeout.

    Returns (task_id, status, outcome) where outcome is 'terminal' or 'timeout'.
    """
    resp = await client.new_task(description, profile=profile, title=f"[eval] {profile}")
    task_id = _task_id_from_new_task(resp)
    if task_id is None:
        return None, None, "submit_failed"
    deadline = now() + timeout_minutes * 60
    while True:
        status_resp = await client.task_status(task_id, "json")
        status = status_resp.get("status") if isinstance(status_resp, dict) else None
        if is_terminal(status):
            return task_id, status, "terminal"
        if now() >= deadline:
            return task_id, status, "timeout"
        await sleep(poll_interval)


async def _run_one_rep(client, cfg, task, model, rep, profile, sleep, now, run_claude):
    """Run a single rep, retrying an infra failure once. Returns a result dict."""
    last_events: list[dict] = []
    for attempt in (1, 2):
        task_id, status, outcome = await _submit_and_wait(
            client, task.description, profile, task.timeout_minutes,
            cfg.task_poll_interval_seconds, sleep, now,
        )
        if outcome in ("submit_failed", "timeout"):
            # No usable transcript / never finished — treat as infra and retry.
            last_events = []
            if attempt == 1:
                continue
            result = scoring_mod.infra_result(last_events)
            result["task_id"] = task_id
            return result

        logs = await client.task_logs(task_id)
        logs_text = logs if isinstance(logs, str) else (logs.get("runner_logs") if isinstance(logs, dict) else "")
        events = transcript_mod.parse_events(logs_text)
        last_events = events

        if transcript_mod.classify(events) == "infra_failure":
            if attempt == 1:
                continue  # retry the rep once
            result = scoring_mod.infra_result(events)
            result["task_id"] = task_id
            return result

        output = await client.task_output(task_id)
        output_text = output if isinstance(output, str) else (output.get("output") if isinstance(output, dict) else None)
        result = scoring_mod.score_rep(
            task, output_text, events, cfg.judge_model, cfg.digest_max_chars, run_claude=run_claude,
        )
        result["task_id"] = task_id
        return result
    # Unreachable, but keep a defined result.
    result = scoring_mod.infra_result(last_events)
    result["task_id"] = None
    return result


async def run_matrix(
    client,
    cfg,
    corpus_tasks,
    run_id,
    no_yield: bool = False,
    sleep=asyncio.sleep,
    now=time.monotonic,
    run_claude=None,
    log=print,
) -> None:
    """Execute the model×workload×rep matrix for ``run_id``, resuming as needed."""
    recorded = recorded_cells(await client.get_eval_run(run_id))
    created_profiles: list[str] = []

    for model in cfg.models:  # strictly sequential per model
        for task in corpus_tasks:
            pending_reps = [r for r in range(task.reps) if (task.workload, model, r) not in recorded]
            if not pending_reps:
                continue
            profile = eval_profile_name(task.workload, model)
            clone_resp = await client.clone_task_profile(task.base_profile, profile, model=model)
            if isinstance(clone_resp, dict) and clone_resp.get("error"):
                log(f"[skip] {profile}: clone failed: {clone_resp['error']}")
                continue
            # Only track profiles we actually created (reused=False) for end-of-run
            # deletion, so we never delete a pre-existing profile we didn't create.
            if isinstance(clone_resp, dict) and clone_resp.get("reused") is False and profile not in created_profiles:
                created_profiles.append(profile)

            for rep in pending_reps:
                if not no_yield:
                    await _yield_to_production(client, cfg.yield_poll_interval_seconds, sleep)
                result = await _run_one_rep(client, cfg, task, model, rep, profile, sleep, now, run_claude)
                await client.record_eval_result(
                    run_id=run_id, workload=task.workload, model=model, rep=rep, **result
                )
                log(f"[recorded] {task.workload} {model} rep{rep}: {result['verdict']} (score={result.get('score')})")

    # Success path only: clean up created profiles and finish the run. On an
    # exception we intentionally do neither, so profiles are reusable and the run
    # is resumable.
    for profile in created_profiles:
        await client.delete_task_profile(profile)
    await client.finish_eval_run(run_id)
