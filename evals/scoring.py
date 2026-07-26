"""Score one rep: classify, assert, digest, judge, and combine into a result.

Order (per eval-judge spec):
  1. Classify infra vs judgeable from the transcript. Infra reps are NOT judged
     and are excluded from model score aggregates (verdict ``infra_failure``).
  2. Evaluate programmatic assertions against the final output + tool calls.
  3. Build a bounded transcript digest and run the judge (always, to capture
     qualitative detail — even when an assertion already failed).
  4. Combine: any failed assertion forces ``fail``; otherwise the judge's pass
     boolean decides. Score is the judge's score (null when unparseable).
"""

from __future__ import annotations

from assertions import all_passed, evaluate_assertions
from digest import build_digest
from judge import judge_rep
import transcript as transcript_mod


def combine_verdict(assertion_results: list[dict], judge_result: dict) -> tuple[str, float | None]:
    """Combine assertions + judge into (verdict, score).

    A failed assertion forces ``fail`` regardless of the judge score. Otherwise
    the judge's ``pass`` decides. Score is always the judge's score (or None).
    """
    score = judge_result.get("score")
    if not all_passed(assertion_results):
        return "fail", score
    return ("pass" if judge_result.get("pass") else "fail"), score


def score_rep(
    corpus_task,
    final_output: str | None,
    events: list[dict],
    judge_model: str,
    digest_max_chars: int = 12000,
    run_claude=None,
) -> dict:
    """Score a judgeable rep end-to-end. Returns a dict shaped for recording.

    Keys: verdict, score, turns, recoveries, error_events, judge_output
    (containing assertions, the judge verdict, and the digest for auditability).
    Callers first check ``transcript.classify(events)``; an infra rep skips this
    and is recorded as ``infra_failure`` without judging.
    """
    metrics = transcript_mod.extract_metrics(events)
    tool_names = transcript_mod.tool_calls(events)
    assertion_results = evaluate_assertions(corpus_task.assertions, final_output, tool_names)
    digest = build_digest(events, max_chars=digest_max_chars)

    judge_kwargs = {} if run_claude is None else {"run_claude": run_claude}
    judge_result = judge_rep(
        judge_model, corpus_task.description, corpus_task.rubric, final_output, digest, **judge_kwargs
    )

    verdict, score = combine_verdict(assertion_results, judge_result)
    return {
        "verdict": verdict,
        "score": score,
        "turns": metrics["turns"],
        "recoveries": metrics["recoveries"],
        "error_events": metrics["error_events"],
        "judge_output": {
            "assertions": assertion_results,
            "judge": judge_result,
            "digest": digest,
        },
    }


def infra_result(events: list[dict]) -> dict:
    """Build the recorded result for an infra-failed rep (no judging)."""
    metrics = transcript_mod.extract_metrics(events)
    return {
        "verdict": "infra_failure",
        "score": None,
        "turns": metrics["turns"],
        "recoveries": metrics["recoveries"],
        "error_events": metrics["error_events"],
        "judge_output": {"classification": "infra_failure"},
    }
