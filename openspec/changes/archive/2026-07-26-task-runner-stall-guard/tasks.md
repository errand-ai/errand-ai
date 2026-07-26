# Tasks — Task-runner stall guard (retrospective)

The implementation already exists in the working tree; the code tasks below are
marked done to reflect that. This change records the spec for it.

## 1. Stall detector

- [x] 1.1 Add `StallDetector` (per-attempt, canonical `(tool, args)` signature with JSON sorted-keys + `repr` fallback) and `AgentStallError` to `task-runner/main.py`, plus `DEFAULT_STALL_REPEAT_LIMIT = 6`.
- [x] 1.2 Read `STALL_REPEAT_LIMIT` from env (default 6, `<= 0` disables, unparseable → warn + default).

## 2. Wire into the agent loop

- [x] 2.1 Construct a fresh `StallDetector` per agent attempt; `record()` each tool call after the `tool_call` event is emitted.
- [x] 2.2 On reaching the limit, emit a `stall_detected` event (`tool`, `repeat_count`, `limit`, `turn_id`) and raise `AgentStallError`.
- [x] 2.3 Handle `AgentStallError`: emit an `error` event with `error_type=stalled`, record the task `failed`, exit non-zero, and do NOT retry.

## 3. Tests & validation

- [x] 3.1 Unit tests in `task-runner/test_main.py`: identical-repeat trip, argument-order insensitivity, tool/arg distinction, disable switch (`limit <= 0`), unserializable-arg fallback, and the blog-to-tweets regression.
- [x] 3.2 Run the task-runner test suite and confirm green.
- [x] 3.3 Run `openspec validate task-runner-stall-guard --strict` and fix any issues.
