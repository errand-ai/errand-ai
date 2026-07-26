# Design — Task-runner stall guard

## Context

The task-runner runs an agent loop (`Runner.run_streamed`) bounded by `MAX_TURNS`
(~200) and wrapped in `MAX_AGENT_RETRIES` for transient failures. It already
rescues malformed tool calls and retries transient LLM errors. What it lacked was
any notion of *progress*: a run that keeps emitting tool calls never trips the
retry/error paths, so a model stuck repeating one call runs until the turn budget
is exhausted (~13 min of wasted inference) or a human kills it. This was observed
in production (a gemma-class model re-reading `/tmp/blogs.work.md` ~13× on the
blog-to-tweets queue).

This is a retrospective design for an already-implemented guard.

## Goals / Non-Goals

**Goals**
- Abort a no-progress loop within a handful of turns instead of at `MAX_TURNS`.
- High precision — never abort a run that is doing legitimate, varied work.
- Operator-tunable and fully disable-able.
- Cheap and legible failure: a clear reason and a structured event, not a timeout.

**Non-Goals**
- Semantic progress detection (varied-but-useless work).
- Cross-attempt or cross-task loop detection.
- Auto-remediation — fail fast and defer to task-level retry/escalation.

## Decisions

### D1. Signal = byte-identical (tool, args) repeats

A stall is counted as the same `tool_name` plus canonicalised `arguments`
repeating. The signature is `tool_name + ":" + json.dumps(args, sort_keys=True,
default=str)`, with a `repr(args)` fallback if the args aren't JSON-serializable.
Canonicalisation (sorted keys) means `{"a":1,"b":2}` and `{"b":2,"a":1}` are one
signature; different tools or different args get independent counters. Healthy
agents vary arguments (different URLs, paths, entry numbers), so identical repeats
are a high-precision stall signal with few false positives — chosen over
fuzzy/semantic heuristics precisely to avoid aborting real work.

### D2. Bounded limit, per-attempt, tunable

`STALL_REPEAT_LIMIT` (default `DEFAULT_STALL_REPEAT_LIMIT = 6`) is the repeat count
that trips the guard. A fresh `StallDetector` is created **per agent attempt** so a
legitimate retry isn't penalised by the previous attempt's calls. `<= 0` disables
the guard: `record()` returns `0`, and the caller's `count and count >= limit`
check never trips. An unparseable env value logs a warning and falls back to the
default.

### D3. Trip after the tool_call event, abort non-retryably

The detector records **after** the `tool_call` event is emitted, so the offending
call is visible in the transcript. On trip it emits a `stall_detected` event
(`tool`, `repeat_count`, `limit`, `turn_id`) and raises `AgentStallError`. Unlike
`ModelBehaviorError` (which auto-enables a tool and retries) or transient errors
(which back off and retry), a stall is **not retryable**: the same prompt + same
model will reproduce it, so the handler records the task `failed` with an error of
type `stalled` and exits `1` rather than consuming a retry. Task-level retry /
escalation still applies above the runner if configured.

## Risks / Trade-offs

- **False positive on legitimately-repeated identical calls.** Rare — real work
  varies arguments — and the default limit (6) leaves headroom. Tunable up, or
  disabled, via `STALL_REPEAT_LIMIT`.
- **Misses varied-but-non-progressing loops.** Accepted: out of scope; broadening
  the heuristic would risk aborting real work. The turn budget remains the
  backstop for those.
