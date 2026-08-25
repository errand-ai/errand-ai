## Why

`context-usage-visibility` (#239) made context pressure measurable, and the first production data it produced exposed two accounting defects that were previously invisible.

The compaction estimator undercounts, so compaction fires later than it appears to. And `read_file` results enter the message list uncapped, while `execute_command` output has been capped since `task-runner-file-tools` was written — one production task carried a single 908,499-character `read_file` result, more than 8x the 112,500-character cap its sibling tool enforces and larger than the entire context ceiling. That task is also the only one whose compaction failed three times in a row and backed off to a 4-turn suppression window.

Neither is currently breaking a task: the measured peak across 216 production tasks is 142,623 tokens against a 150,000 ceiling, and the fallback trim covers what compaction misses. Both are degrading silently, and both are now cheap to fix because there is finally a measured number to correct against.

## What Changes

- **Calibrate the compaction estimator against measured usage.** `_estimate_tokens` serialises only the message list, while the real prompt also carries the instructions and tool schemas — a roughly fixed ~5,400-token blind spot (measured: 501 estimated against 5,925 reported). It shrinks proportionally as history grows (~4% at 145k), so compaction fires late rather than never. Now that `llm_turn_end` reports the provider's own `input_tokens` per turn, the estimator can be corrected against that measurement instead of guessed at — either calibrated by the observed offset or replaced by the previous turn's measurement plus a delta.
- **Cap a tool result at ingest, not just `execute_command` output.** `MAX_TOOL_OUTPUT_CHARS` (`MAX_CONTEXT_TOKENS * CHARS_PER_TOKEN * 0.25`) is applied at one call site inside `execute_command`. Apply an equivalent bound to `read_file`, with the same truncation marker naming the elided size, so no single tool result can exceed the context ceiling it must fit inside.
- **Verify the compaction-failure correlation before treating it as fixed.** The 908k-char result and the three `compaction_failed` events co-occur on one task; the causal link (a summarisation call handed a message larger than its own window) is plausible but unproven. Confirm it from the telemetry rather than assuming it.

## Capabilities

### New Capabilities

<!-- None. Both changes tighten existing behaviour rather than introducing new surface. -->

### Modified Capabilities

- `task-runner-context-compaction`: the trigger threshold becomes a corrected estimate rather than a raw serialisation of the message list, so "compaction fires at the configured ceiling" becomes true rather than approximately true.
- `task-runner-file-tools`: the existing output size cap is currently scoped to `execute_command` alone; the requirement extends to `read_file` so that the cap describes tool results generally rather than one tool.

## Impact

- `task-runner/main.py` — `_estimate_tokens` (line ~1331), `MAX_TOOL_OUTPUT_CHARS` (~660) and its single application site (~960), and the `read_file` tool.
- `task-runner/tests/` — existing compaction and file-tool suites; the estimator change needs a test that pins the corrected value against a known-good measurement rather than asserting an arbitrary constant.
- No API, schema, or frontend impact. No migration.
- Behavioural risk: a corrected (larger) estimate means compaction fires *earlier* than today, so tasks that currently sit just under the trigger will begin compacting. That is the intended fix, but it changes when existing workloads compact and should be verified against the measured series in Loki after deploy.
