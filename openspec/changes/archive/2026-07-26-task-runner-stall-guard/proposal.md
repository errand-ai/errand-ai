## Why

A weak model can get stuck in a no-progress loop — repeating the *same* tool call
with the *same* arguments indefinitely (re-reading one file, re-`discover_tools`-ing
already-enabled tools). `MAX_TURNS` (~200) is only a hard ceiling: a stuck run
burns the entire budget (~13 minutes of inference) before it trips. This actually
happened — a gemma-class model looped ~13× re-reading `/tmp/blogs.work.md` on the
blog-to-tweets queue and had to be killed manually.

The runner already recovers from *transient* failures (retries, tool-call rescue)
but has no defence against a run that is technically "making tool calls" yet
making no progress. That failure mode is invisible until the turn budget or a
human intervenes.

This change is **retrospective**: it documents and specs a stall-guard that has
already been implemented in `task-runner/main.py`.

## What Changes

- Add a **no-progress loop guard** to the task-runner agent loop: a `StallDetector`
  counts byte-identical `(tool_name, arguments)` tool-call signatures within a
  single agent attempt. When one signature repeats `STALL_REPEAT_LIMIT` times
  (default 6), the run is aborted as a stall.
- The signature is canonical (JSON with sorted keys, `repr` fallback for
  non-serializable args), so argument key-order doesn't create false distinctions
  and different tools / different args count independently. Healthy runs vary
  their arguments, so an identical-signature repeat is a high-precision signal.
- On trip: emit a `stall_detected` structured event (naming the tool, repeat
  count, limit, turn), then raise `AgentStallError`. The handler records the task
  as `failed` with a `stalled` error and exits **without retrying** — the same
  prompt + model would only stall again, so failing fast is cheaper and clearer
  than exhausting `MAX_TURNS`.
- The guard is **per-attempt** (a legitimate retry starts with a clean budget)
  and **operator-tunable** via `STALL_REPEAT_LIMIT`; `<= 0` disables it entirely.

## Capabilities

### Modified Capabilities

- `task-runner-error-resilience`: add "No-progress loop detection (stall guard)" —
  a dirty/stuck run that repeats an identical tool call past a bounded limit is
  detected and aborted non-retryably, rather than running to `MAX_TURNS`.
- `structured-task-events`: add the `stall_detected` event emitted when the guard
  trips.

## Impact

- **Task-runner** — `task-runner/main.py`: `StallDetector`, `AgentStallError`,
  `DEFAULT_STALL_REPEAT_LIMIT`, the per-attempt detector wired into the streaming
  tool-call path, and the `AgentStallError` handler. `task-runner/test_main.py`:
  unit tests (signature canonicalization, tool/arg distinction, disable switch,
  unserializable-arg fallback, the blog-to-tweets regression).
- **Config** — new `STALL_REPEAT_LIMIT` env var (default 6; `<= 0` disables).
- No server, API, database, or Helm changes. Behaviour change is limited to the
  task-runner aborting a class of stuck run earlier and more legibly.

## Non-goals

- Detecting *semantic* non-progress (varied arguments that still make no headway).
  The guard is deliberately high-precision — only byte-identical repeats — to
  avoid aborting legitimate work; broader stall heuristics are out of scope.
- Automatic remediation (re-prompting, model switching) — the run fails fast and
  the existing task retry/escalation machinery takes over at the task level.
