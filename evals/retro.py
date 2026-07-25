"""Retro-judging mode: baseline historical output quality per workload.

Phase-zero calibration before any live bake-off. For a workload, retro searches
historical *non-eval* tasks, retrieves each transcript, attributes the model from
its ``llm_turn_start`` events, judges the historical output against the workload
rubric, and records results under a ``mode='retro'`` run. It never clones
profiles or submits tasks. Tasks with no parseable model (or classified as infra)
are skipped and reported, drawing further samples when available.
"""

from __future__ import annotations

from digest import build_digest
from judge import judge_rep
import transcript as transcript_mod


async def run_retro(
    client,
    cfg,
    workload: str,
    sample: int,
    run_id: str,
    rubric: str,
    run_claude=None,
    log=print,
) -> dict:
    """Judge up to ``sample`` historical tasks for ``workload``. Returns a summary.

    Candidates are searched newest-first; the driver walks them, skipping any it
    cannot use (no transcript model, infra failure, no output), until ``sample``
    are recorded or candidates are exhausted.
    """
    # Over-fetch so skips still leave enough usable candidates.
    candidates = await client.search_tasks(
        profile=workload, is_eval=False, status="archived", limit=min(sample * 4, 200)
    )
    if not isinstance(candidates, list):
        candidates = []

    recorded = 0
    skipped: list[dict] = []
    for cand in candidates:
        if recorded >= sample:
            break
        task_id = cand.get("id")
        logs = await client.task_logs(task_id)
        logs_text = logs if isinstance(logs, str) else (logs.get("runner_logs") if isinstance(logs, dict) else "")
        events = transcript_mod.parse_events(logs_text)

        model = transcript_mod.attribute_model(events)
        if model is None:
            skipped.append({"task_id": task_id, "reason": "no_model_in_transcript"})
            continue
        if transcript_mod.classify(events) == "infra_failure":
            skipped.append({"task_id": task_id, "reason": "infra_failure"})
            continue

        output = await client.task_output(task_id)
        output_text = output if isinstance(output, str) else (output.get("output") if isinstance(output, dict) else None)
        if not output_text:
            # No output to judge — don't record an empty-output task as a model
            # failure in the baseline; skip and report it.
            skipped.append({"task_id": task_id, "reason": "no_output"})
            continue
        digest = build_digest(events, max_chars=cfg.digest_max_chars)
        judge_kwargs = {} if run_claude is None else {"run_claude": run_claude}
        verdict_obj = judge_rep(
            cfg.judge_model, cand.get("title") or workload, rubric, output_text, digest, **judge_kwargs
        )
        metrics = transcript_mod.extract_metrics(events)
        await client.record_eval_result(
            run_id=run_id,
            workload=workload,
            model=model,
            rep=0,
            verdict="pass" if verdict_obj.get("pass") else "fail",
            task_id=task_id,
            score=verdict_obj.get("score"),
            turns=metrics["turns"],
            recoveries=metrics["recoveries"],
            error_events=metrics["error_events"],
            judge_output={"judge": verdict_obj, "digest": digest},
        )
        recorded += 1
        log(f"[retro] {workload} {model} task={task_id}: {'pass' if verdict_obj.get('pass') else 'fail'} (score={verdict_obj.get('score')})")

    return {"recorded": recorded, "skipped": skipped, "candidates": len(candidates)}
