## 1. Branch and version

- [ ] 1.1 Branch from `main` as `context-accounting-correctness`
- [ ] 1.2 Bump `VERSION` (minor — behaviour change to when compaction fires, no breaking API)

## 2. Cap the tool result

Do this first. It is the smaller of the two fixes, it is independently verifiable, and landing it before the estimator change means the estimator can be observed without an outsized message distorting the measurement.

- [ ] 2.1 Extract the truncation currently inline in `_format_command_output` into a helper taking the text and a caller-specific guidance suffix. Keep `MAX_TOOL_OUTPUT_CHARS` as the single source of the bound
- [ ] 2.2 Call the helper from `execute_command`, preserving today's file-path-tools guidance verbatim so existing behaviour is unchanged
- [ ] 2.3 Call the helper from `read_file` with guidance pointing at its own `offset`/`limit` parameters. The truncation must be applied above `_read_file_sync`, not inside it
- [ ] 2.4 Confirm the `WARNING` log fires for both paths, naming the tool, so a task hitting the cap is greppable in the container log
- [ ] 2.5 Tests: content within cap unchanged; content over cap truncated with the right guidance per tool; cap scales with `MAX_CONTEXT_TOKENS`; truncated output including the suffix does not itself exceed the cap
- [ ] 2.6 Test the binary-file path still returns its existing guidance rather than a truncated blob — `read_file` raises `UnicodeDecodeError` before size is ever considered, and that ordering must not change

## 3. Correct the compaction estimate

- [ ] 3.1 Carry the most recent measured `input_tokens` from `llm_turn_end` where `_compact_context` can read it. Treat an all-zero usage block as no measurement, per the rule established in #239 — baselining off zero would be worse than today
- [ ] 3.2 Derive the trigger size as last measurement plus the serialised size of messages appended since it. Decide and document how "appended since" is tracked; the message list is rebuilt each turn, so an index is not stable across turns
- [ ] 3.3 Implement the fallback: serialised size plus a conservative fixed overhead, used on the first turn and whenever no measurement is available
- [ ] 3.4 Keep `_estimate_tokens` itself intact and honest about what it measures. It is still the right function for sizing a message list; it is only wrong as a proxy for the prompt
- [ ] 3.5 Tests: trigger uses the measurement when one exists; falls back on the first turn; treats all-zero usage as absent; does not compact below the ceiling; still falls back to `_trim_context_window` when summarisation fails

## 4. Test the correction against reality

- [ ] 4.1 Pin the estimator test against a recorded (messages, reported `input_tokens`) pair rather than an arbitrary constant, so the test fails if the correction stops tracking the real prompt
- [ ] 4.2 Confirm the corrected size converges toward the reported figure as history grows, rather than merely being larger than before

## 5. Investigate the compaction-failure hypothesis

Separate from the fixes, and explicitly allowed to conclude "not proven".

- [ ] 5.1 From the telemetry for task `b9679638`, establish whether the 908,499-char `read_file` result was in the summarised portion on each of the three `compaction_failed` events
- [ ] 5.2 Check whether other tasks that failed compaction did so without an oversized result present. A different signature there means the oversized message is not the general cause
- [ ] 5.3 Record the conclusion in the change, including if it is negative. If the cap does not explain the failures, say so and open a follow-up rather than letting the correlation stand as a fix

## 6. Verify

- [ ] 6.1 Backend, task-runner and frontend suites green
- [ ] 6.2 `openspec validate --specs` passes, as the CI guard requires
- [ ] 6.3 Run a task that reads a large file and confirm the truncation marker appears with pagination guidance, and that the agent can act on it
- [ ] 6.4 After deploy, compare compaction frequency and peak `input_tokens` in Loki against the pre-change baseline: peak 142,623 across 216 tasks, 8 tasks reaching the trigger in 30 days
- [ ] 6.5 Confirm compaction frequency rises only for tasks that were near the ceiling. A rise for tasks nowhere near it means the correction over-shoots and should be reverted, not tuned in production

## 7. Follow-ups (not this change)

- [ ] 7.1 Cap every tool result centrally rather than per tool. Correct destination, but it means wrapping SDK tool dispatch and covers MCP results whose sizes are not yet characterised — deliberately out of scope here
- [ ] 7.2 Decide whether the fallback overhead constant should be configurable, or whether a hard-coded conservative value is right for a path that only applies before the first measurement
