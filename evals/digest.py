"""Bounded transcript digest for the judge.

The judge sees a compact, event-only digest — the sequence of tool calls (names +
truncated arguments) and truncated tool results — not the raw ``runner_logs``,
which contains pip noise and can exceed the judge's context (job-research p90 = 66
turns, ~240 kB). The digest is capped at a configurable character budget.
"""

from __future__ import annotations

import json

_ARG_TRUNCATE = 200
_RESULT_TRUNCATE = 300


def _truncate(value, limit: int) -> str:
    text = value if isinstance(value, str) else json.dumps(value, default=str)
    text = " ".join(text.split())  # collapse whitespace/newlines
    return text if len(text) <= limit else text[:limit] + "…"


def build_digest(events: list[dict], max_chars: int = 12000) -> str:
    """Render an event-only digest of tool calls and results, capped at max_chars.

    Only ``tool_call``, ``tool_result``, ``error``, and turn markers are included;
    reasoning/thinking and non-event log noise are omitted. When the budget is
    exceeded, the digest is truncated and a marker line notes how many events were
    dropped, so the judge always sees a bounded but honest view.
    """
    lines: list[str] = []
    for e in events:
        t = e["type"]
        data = e.get("data", {})
        if t == "llm_turn_start":
            lines.append(f"[turn {data.get('turn_id', '?')}] model={data.get('model', '?')}")
        elif t == "tool_call":
            lines.append(f"  → {data.get('tool', '?')}({_truncate(data.get('args', {}), _ARG_TRUNCATE)})")
        elif t == "tool_result":
            result = data.get("result", data.get("output", data))
            lines.append(f"    ⇒ {_truncate(result, _RESULT_TRUNCATE)}")
        elif t == "error":
            lines.append(f"  ! error: {_truncate(data.get('message', ''), _RESULT_TRUNCATE)}")
        elif t == "tool_call_recovered_from_reasoning":
            names = data.get("function_names", [])
            lines.append(f"  ~ recovered tool call(s) from reasoning: {', '.join(names)}")

    # Keep a chronological *prefix* — stop at the first line that would overflow
    # so the marker's "N further lines omitted" is accurate and the digest reads
    # coherently from the start of the transcript.
    kept: list[str] = []
    used = 0
    for i, line in enumerate(lines):
        if used + len(line) + 1 > max_chars:
            kept.append(f"[digest truncated: {len(lines) - i} further event line(s) omitted to fit {max_chars} chars]")
            break
        kept.append(line)
        used += len(line) + 1
    return "\n".join(kept)
