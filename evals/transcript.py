"""Parse a task's runner transcript (JSONL event stream) and derive metrics.

The task-runner emits one JSON object per line to stderr — ``{"type": ..., "data":
{...}}`` — captured into a task's ``runner_logs``. The raw log is interleaved with
non-JSON noise (pip output, tracebacks), so we extract only the parseable event
lines and ignore the rest.

Event types we rely on (see task-runner/main.py emit_event calls):
  agent_start / agent_end   — the agent loop ran / finished (output in agent_end)
  llm_turn_start            — one model turn; carries the model name
  tool_call                 — {tool, args, turn_id}
  error                     — {message}
  tool_call_recovered_from_reasoning — a local model's malformed tool call rescued
  mcp_connected             — MCP servers connected
"""

from __future__ import annotations

import json

# Substrings (lowercased) in an `error` event message that mark an infrastructure
# failure rather than a model-quality failure. Deliberately specific to avoid
# swallowing ordinary task errors; calibrated against history in retro mode.
_INFRA_ERROR_PATTERNS = (
    "no matching distribution",
    "could not install",
    "failed to install",
    "pip install",
    "requirements.txt",
    "error installing skill",
    "failed to connect to mcp",
    "mcp server connection",
    "mcp connection failed",
    "connection refused",
    "zombie",
)


def parse_events(runner_logs: str | None) -> list[dict]:
    """Extract the JSONL event objects from a raw runner log, in order.

    Lines that are not JSON objects with a ``type`` key are skipped (pip output,
    tracebacks, blank lines).
    """
    events: list[dict] = []
    if not runner_logs:
        return events
    for line in runner_logs.splitlines():
        line = line.strip()
        if not line or not line.startswith("{"):
            continue
        try:
            obj = json.loads(line)
        except ValueError:
            continue
        if isinstance(obj, dict) and "type" in obj:
            obj.setdefault("data", {})
            events.append(obj)
    return events


def event_types(events: list[dict]) -> list[str]:
    return [e["type"] for e in events]


def tool_calls(events: list[dict]) -> list[str]:
    """Tool names from `tool_call` events, in order (may repeat)."""
    return [e["data"].get("tool") for e in events if e["type"] == "tool_call" and e["data"].get("tool")]


def extract_metrics(events: list[dict]) -> dict:
    """Turn count, recovery count, and error-event count from the transcript."""
    turns = recoveries = errors = 0
    for e in events:
        t = e["type"]
        if t == "llm_turn_start":
            turns += 1
        elif t == "tool_call_recovered_from_reasoning":
            recoveries += 1
        elif t == "error":
            errors += 1
    return {"turns": turns, "recoveries": recoveries, "error_events": errors}


def attribute_model(events: list[dict]) -> str | None:
    """Model name from the first `llm_turn_start` event, or None.

    Used by retro mode to attribute a historical task's transcript to a model.
    """
    for e in events:
        if e["type"] == "llm_turn_start":
            model = e["data"].get("model")
            if model and model != "unknown":
                return model
    return None


def agent_end_output(events: list[dict]) -> str | None:
    """The final result text from the `agent_end` event, if present.

    The authoritative final output comes from the `task_output` MCP call; this is
    a transcript-side fallback and lets tests reason about the output.
    """
    for e in reversed(events):
        if e["type"] == "agent_end":
            output = e["data"].get("output")
            if isinstance(output, dict):
                return output.get("result")
            if isinstance(output, str):
                return output
    return None


def classify(events: list[dict]) -> str:
    """Classify a rep as ``infra_failure`` or ``judgeable``.

    A rep is infra when the agent never started (no ``agent_start`` — e.g. skill
    install wedged startup) or an ``error`` event matches a known infrastructure
    pattern (skill install, MCP connection, zombie recovery). Everything else —
    including a completed-but-wrong result — is judgeable (a model failure).
    """
    types = event_types(events)
    if "agent_start" not in types:
        return "infra_failure"
    for e in events:
        if e["type"] == "error":
            msg = (e["data"].get("message") or "").lower()
            if any(pat in msg for pat in _INFRA_ERROR_PATTERNS):
                return "infra_failure"
    return "judgeable"
