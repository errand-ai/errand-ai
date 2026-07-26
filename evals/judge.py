"""LLM-as-judge via the ``claude`` CLI headless.

The judge runs on the ``claude`` CLI (print mode) under the Max subscription —
deliberately independent of the LiteLLM gateway under test, with zero marginal
cost. It receives the task description, rubric, final output, and a bounded
transcript digest, and must return a strict JSON verdict. A non-JSON response is
retried once; a second failure records a null score with the raw responses
preserved so the rep can be re-judged later from retained evidence.
"""

from __future__ import annotations

import json
import subprocess

_JUDGE_TIMEOUT_SECONDS = 300

_PROMPT_TEMPLATE = """You are grading the output of an autonomous task agent against a rubric.

Return ONLY a JSON object (no prose, no code fence) with exactly these keys:
  "pass": boolean — whether the output acceptably satisfies the task and rubric
  "score": integer 0-10 — overall quality
  "reasons": array of short strings — per-criterion justification

## Task description
{description}

## Rubric
{rubric}

## Final output produced by the agent
{output}

## Transcript digest (tool calls and truncated results)
{digest}
"""


def build_prompt(description: str, rubric: str, final_output: str | None, digest: str) -> str:
    return _PROMPT_TEMPLATE.format(
        description=description,
        rubric=rubric,
        output=final_output or "(no output produced)",
        digest=digest or "(no transcript events)",
    )


def _default_run_claude(prompt: str, model: str) -> str:
    """Invoke `claude -p` headless and return its stdout (the model's text)."""
    proc = subprocess.run(
        ["claude", "-p", "--model", model, "--output-format", "text"],
        input=prompt,
        capture_output=True,
        text=True,
        timeout=_JUDGE_TIMEOUT_SECONDS,
    )
    if proc.returncode != 0:
        raise RuntimeError(f"claude CLI exited {proc.returncode}: {proc.stderr.strip()[:500]}")
    return proc.stdout


def _extract_json(text: str) -> dict | None:
    """Parse the first JSON object from the model's text, tolerating a code fence.

    Uses a balanced-brace scan (string- and escape-aware) rather than a greedy
    ``{.*}`` regex, so extra brace-delimited spans elsewhere in the response
    don't cause the first valid object to be over-captured and fail to parse.
    """
    if not text:
        return None
    candidate = text.strip()
    try:
        obj = json.loads(candidate)
        return obj if isinstance(obj, dict) else None
    except ValueError:
        pass
    return _first_json_object(candidate)


def _first_json_object(text: str) -> dict | None:
    """Return the first balanced-brace ``{...}`` span that parses as a dict."""
    start = text.find("{")
    while start != -1:
        depth = 0
        in_str = False
        esc = False
        for i in range(start, len(text)):
            c = text[i]
            if in_str:
                if esc:
                    esc = False
                elif c == "\\":
                    esc = True
                elif c == '"':
                    in_str = False
            elif c == '"':
                in_str = True
            elif c == "{":
                depth += 1
            elif c == "}":
                depth -= 1
                if depth == 0:
                    try:
                        obj = json.loads(text[start : i + 1])
                    except ValueError:
                        break  # this span isn't valid JSON — try the next '{'
                    if isinstance(obj, dict):
                        return obj
                    break
        start = text.find("{", start + 1)
    return None


def _normalize_verdict(obj: dict, raw_responses: list[str]) -> dict:
    """Coerce a parsed judge object into the recorded verdict shape."""
    passed = bool(obj.get("pass"))
    score = obj.get("score")
    try:
        score = float(score) if score is not None else None
    except (TypeError, ValueError):
        score = None
    return {
        "parsed": True,
        "pass": passed,
        "score": score,
        "reasons": obj.get("reasons", []),
        "raw": raw_responses,
    }


def judge_rep(
    model: str,
    description: str,
    rubric: str,
    final_output: str | None,
    digest: str,
    run_claude=_default_run_claude,
) -> dict:
    """Judge one rep. Returns a verdict dict.

    On success: ``{parsed: True, pass, score, reasons, raw:[...]}``. After two
    unparseable responses: ``{parsed: False, pass: False, score: None, reasons: [],
    raw: [resp1, resp2]}`` — the raw responses are preserved for later re-judging.
    ``run_claude`` is injectable for testing.
    """
    prompt = build_prompt(description, rubric, final_output, digest)
    raw_responses: list[str] = []
    for _attempt in range(2):
        try:
            response = run_claude(prompt, model)
        except Exception as exc:  # noqa: BLE001 — a CLI failure must not crash the run
            raw_responses.append(f"<claude error: {exc}>")
            continue
        raw_responses.append(response)
        obj = _extract_json(response)
        if obj is not None:
            return _normalize_verdict(obj, raw_responses)
    return {"parsed": False, "pass": False, "score": None, "reasons": [], "raw": raw_responses}
