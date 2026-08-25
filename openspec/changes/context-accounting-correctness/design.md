## Context

`context-usage-visibility` (#239) added `llm_turn_end`, which carries the provider's own `input_tokens` for every model call. That measurement is new, and it is what makes both defects here fixable rather than merely known.

**The estimator.** `_estimate_tokens` (`task-runner/main.py`) is `len(json.dumps(messages)) // CHARS_PER_TOKEN`. It sees only the message list. The real prompt also carries the agent instructions and the JSON schema of every registered tool, neither of which appear in `messages`. Measured on a real run: 501 estimated against 5,925 reported — a roughly fixed ~5,400-token blind spot. Because it is roughly fixed, it matters least when it matters least: ~4% of a 145k history, but an order of magnitude on a small one. The practical effect is that compaction fires late, by about that margin.

**The cap.** `MAX_TOOL_OUTPUT_CHARS = MAX_CONTEXT_TOKENS * CHARS_PER_TOKEN * 0.25` is 112,500 characters at the current ceiling. It is applied in exactly one place: `_format_command_output`, on the `execute_command` path. `read_file` calls `_read_file_sync` and returns the result unbounded. Production shows a single `read_file` result of 908,499 characters — 8x the cap its sibling enforces, and larger than the entire 150,000-token ceiling it has to fit inside.

Neither defect is currently failing tasks. Peak measured context across 216 production tasks is 142,623 against a 150,000 ceiling, and the fallback trim catches what compaction misses. Both degrade quietly, which is why they survived this long.

## Goals / Non-Goals

**Goals:**

- Make the compaction trigger fire at the configured ceiling rather than approximately at it, using the measurement that now exists instead of a better guess.
- Bound any single tool result below the context ceiling it must fit inside, closing the `read_file` gap against the cap `execute_command` already honours.
- Establish whether the 908k-char result actually caused the three co-occurring compaction failures, rather than assuming it from correlation.

**Non-Goals:**

- Changing `MAX_CONTEXT_TOKENS` itself, or how it is resolved. That is `context-ceiling-research`.
- Surfacing any of this in the UI or on the task record. That is `context-usage-observability`.
- A generic interceptor that caps every tool result centrally. Attractive, but it means wrapping the SDK's tool dispatch; see Decisions.
- Making `_estimate_tokens` exact. It is a trigger heuristic, not an accounting system.

## Decisions

### 1. Correct the estimate from the last measurement, not from a tuned constant

**Chosen:** carry the most recent `input_tokens` from `llm_turn_end` and use it as the baseline for the next turn's estimate, adding the serialised size of messages appended since that measurement. Fall back to today's behaviour plus a conservative fixed overhead when no measurement is available yet (the first turn, or a provider that reports no usage).

**Why:** the blind spot is not one number. It is the instructions plus the tool schemas, and the tool schemas change with the tool set — `discover_tools` can enlarge them mid-task. A tuned constant would be correct for one configuration and silently wrong for the next. The previous turn's measurement already includes whatever the prompt actually carried, so the correction tracks the real prompt without anyone having to enumerate what is in it.

**Alternatives considered:**

- *Add a fixed `PROMPT_OVERHEAD_TOKENS` constant (~5,400).* Simplest, and better than today. Rejected as the primary mechanism because it hard-codes a measurement taken against one tool set, and would drift silently. Retained as the fallback, where being approximately right beats having nothing.
- *Count the instructions and tool schemas directly.* Most faithful, but it reaches into SDK internals for the serialised schema representation and would break on SDK upgrades. The measurement gives the same answer without the coupling.
- *Ask the provider to count tokens.* An extra round trip per turn on the hot path, for a threshold check. Not worth it.

**Consequence to accept:** a corrected estimate is larger, so compaction fires *earlier* than today — this is the fix, but it changes when existing workloads compact. Deployment must be watched, not assumed.

### 2. Cap `read_file` by reusing the existing bound, applied in one shared helper

**Chosen:** extract the truncation currently inline in `_format_command_output` into a helper that takes the text and a caller-specific guidance suffix, and call it from both `execute_command` and `read_file`. `MAX_TOOL_OUTPUT_CHARS` stays the single source of the bound.

**Why:** the cap already exists and is already specified; the defect is that it is applied at one call site rather than expressed as a property of tool results. One helper makes the next tool that returns bulk text a one-line change rather than a rediscovery of this bug.

**The guidance differs per tool, which is the point.** `execute_command`'s truncation message points at file-path-based tools, because there is nothing else it can offer. `read_file` already takes `offset` and `limit`. So its truncation message can tell the agent to paginate — a remedy it can act on immediately, in the same tool, without abandoning what it was doing. That asymmetry is worth preserving rather than flattening into one shared message.

**Alternatives considered:**

- *Cap centrally in the agent loop, over every tool result.* Correct in principle and the eventual destination. Rejected here because it means wrapping SDK tool dispatch, it would catch MCP tool results whose sizes are not yet characterised, and it turns a two-line fix into a change with its own risk profile. Recorded as a follow-up rather than smuggled into a correctness fix.
- *Cap inside `_read_file_sync`.* Puts truncation below the layer that knows about tool-result budgets, and makes the sync helper harder to reuse. Rejected.

### 3. Confirm the compaction-failure link before claiming it fixed

**Chosen:** treat the correlation as a hypothesis with a specific test. The claim is that a summarisation call handed a ~227k-token message cannot succeed. Verify from the telemetry that the failing compactions on task `b9679638` had that message in the summarised portion, and that tasks failing compaction without an oversized result show a different signature.

**Why:** one task exhibits both the 908k-char result and three `compaction_failed` events. That is one sample. Shipping the cap and declaring the compaction failures fixed would be a post-hoc conclusion, and if the real cause is elsewhere it stays unfixed while looking closed.

## Risks / Trade-offs

- **A corrected estimate compacts earlier, changing behaviour for tasks that today sit just under the trigger** → This is the intended effect, but it lands on live workloads. Verify against the measured Loki series after deploy: compaction frequency should rise for tasks previously near the ceiling, and peak `input_tokens` should fall. If compaction frequency rises for tasks nowhere near the ceiling, the correction is over-shooting and should be reverted rather than tuned in production.
- **Truncating `read_file` could break a task that legitimately needs a whole large file** → Mitigated by the pagination advice, which `read_file` can honour directly via `offset`/`limit`. The cap is 112,500 characters; anything larger cannot fit in context whole regardless, so the alternative to truncation is not success but a blown context window.
- **The estimator fallback path is the one least exercised in tests and most likely in production edge cases** (first turn, provider reporting no usage) → Test it explicitly rather than only the happy path. Note that #239 established a usage block of all zeros means *no measurement*, not a measurement of zero; the fallback must treat it that way or it will baseline off zero.
- **Two independent fixes in one change** → They share a root (context accounting that does not reflect reality) and both are small and task-runner-local, but they can be verified separately and should be, so a problem with one does not obscure the other.

## Migration Plan

No schema change, no API change, no migration. Deploy is the normal PR → image → ArgoCD path.

Rollback is per-fix: the cap is a helper call that can be removed, and the estimator correction is guarded by whether a measurement exists, so forcing the fallback path restores today's behaviour plus a constant.

## Open Questions

- Should the fallback overhead constant be configurable, or is a hard-coded conservative value right for something that only applies before the first measurement lands?
- Does the truncation marker on `read_file` need to report the total line count as well as the character count? Pagination advice is more actionable with a target, but the line count means reading the file twice.
