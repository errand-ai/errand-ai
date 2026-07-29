## Context

Compaction replaces the oldest part of a conversation with an LLM-generated summary when the estimated token count crosses `MAX_CONTEXT_TOKENS`. It is invoked from `filter_model_input`, which the agents SDK calls before **every** model request, so its cost and its failure behaviour are per-turn concerns, not per-task ones.

The mechanism has a 0% success rate over the last fourteen days: 6 timeouts and 13 empty summaries, 19 failures from 19 attempts. Each failure silently falls through to `_trim_context_window`. The evidence, including the confirming traceback and the timing analysis that distinguishes the two modes, is in the proposal.

Three properties of the current implementation matter for the design:

- The compaction call is a **separate synchronous `OpenAI()` client**, not the agents SDK path. It has its own timeout, its own `max_tokens`, and does not inherit `LLM_REQUEST_TIMEOUT` — deliberately, per the comment at `task-runner/main.py:1719`.
- `_trim_context_window` stops the instant the estimate is `<= MAX_CONTEXT_TOKENS`. It performs the minimum possible trim.
- There is no state tracking compaction outcomes across turns. Nothing prevents an identical retry on the next call.

The existing spec (`task-runner-context-compaction`) describes only the success path. Nothing in it constrains what happens on failure, which is why total failure went unnoticed.

## Goals / Non-Goals

**Goals:**

- Compaction succeeds for the model configurations actually in use, including local and free-tier endpoints.
- A compaction failure costs one attempt, not one per turn.
- When compaction does fail, the logs say enough to identify which of the two modes it was and why.
- The compaction model, timeout and token budget are operator-settable at runtime rather than fixed at deploy time.

**Non-Goals:**

- Surfacing context usage in the UI or to Loki — that is `context-usage-visibility`, which should land second.
- Changing `MAX_TOOL_OUTPUT_CHARS` or otherwise capping tool output. Large tool results are a contributing factor but a separate decision.
- Replacing the summarisation approach, prompt, or the `KEEP_RECENT_TOKENS` split point.
- Making `MAX_CONTEXT_TOKENS` model-aware. That depends on measurements this change does not produce.

## Decisions

**Settings resolved server-side, injected as env vars, with env override preserved.** The runner already receives `LLM_REQUEST_TIMEOUT`, `MAX_TURNS` and `LOG_LEVEL` this way, so compaction settings follow an established path rather than inventing one. Keeping the env vars working as overrides means existing deployments that set `COMPACTION_MODEL` are not broken, and matches the registry's documented env → DB → default order. The alternative — reading settings from the runner directly — was rejected: the runner has no database access by design.

**`compaction_model` must be registered in `MODEL_SETTING_KEYS`.** Not optional. The shared settings card writes `{provider_id, model_id}` while the backend resolves `model`; `normalize_model_setting_value` mirrors them only for keys in that set. Omitting it reproduces the `OPENAI_MODEL` defect fixed in `selective-mcp-server-defaults` — a model selected in the UI that resolves to an empty string at runtime.

**Default timeout 180s, up from 30s.** The floor is set by generation, not by the network: 2048 tokens at the 40–80 tok/s a local MoE sustains is 25–50 seconds before any prefill. 30s cannot be met. 180s clears that with margin for a slow prefill on a large context. The obvious objection — that a generous timeout lets a hung call stall a task — is answered by the backoff decision below, which bounds the exposure to a single occurrence rather than one per turn. A shorter timeout with retries was considered and rejected: retries multiply the cost of the failure mode we are trying to eliminate.

**Default token budget 4096, up from 2048, and configurable.** The empty-summary evidence points at a budget consumed by reasoning tokens before any content is emitted. Doubling it does not *guarantee* a reasoning model leaves room for the summary, but it converts a certain failure into a likely success, and configurability lets an operator raise it further for a specific model. Note this is a mitigation, not a diagnosis — which is why the diagnostics below matter more.

**Trim to a fraction of the ceiling, not to the ceiling.** The current minimum-trim behaviour guarantees the next tool result re-crosses the threshold, which is what produced the observed 12-second re-trigger cadence. Trimming to ~60% of `MAX_CONTEXT_TOKENS` buys several turns of headroom per fallback. The cost is discarding more history in a single step; the benefit is discarding less overall, because the alternative is repeated trims in quick succession. The fraction is a constant rather than a setting — one more knob for a fallback path is not worth the configuration surface.

**Exponential, turn-counted backoff, reset on success.** After the *n*th consecutive failure, skip compaction for the next 2ⁿ turns (capped), falling through to trim-with-headroom. This bounds a broken configuration to a handful of wasted calls per task instead of one per turn, while still recovering automatically if the failure was transient. Two alternatives were rejected: permanently disabling compaction after one failure discards a working mechanism on a blip, and a wall-clock cooldown behaves unpredictably when turn duration varies by two orders of magnitude between local and cloud models.

**Diagnose the empty-summary path specifically.** On empty content, log `finish_reason`, the content length, and whether a reasoning/thinking field was populated — at `WARNING`, because production runs the runner at that level and an `INFO` line would be discarded exactly as "Context compaction triggered" has been. This is the single most valuable line in the change: it distinguishes "the model refused" from "thinking consumed the budget" and tells the operator which lever to pull.

## Risks / Trade-offs

**A generous timeout stalls a task that would previously have failed fast** → Backoff bounds it to one occurrence per escalation step rather than every turn. Net exposure is lower than today, where a 30s failure repeats indefinitely.

**Trimming to 60% discards history that compaction might have summarised** → Only on the fallback path, which is by definition already degraded. Repeated minimal trims discard more in aggregate, as the observed spiral shows.

**Pointing `compaction_model` at a cloud model introduces per-task cost where there was none** → It is opt-in and operator-visible. Worth stating plainly in the setting's description rather than discovering on a bill.

**Raising `max_tokens` does not fix a reasoning model that always thinks past the budget** → Accepted. The diagnostics are what turn this from a guess into a decision; disabling thinking for the compaction call is the likely follow-up and is listed as an open question rather than assumed.

**Backoff could mask a genuine regression** → It logs on entry and on reset, so a task that never compacts is visible rather than silent — the opposite of today's behaviour.

## Migration Plan

No schema or data migration. Three new settings rows are created on first write; until then the resolver returns the new defaults, so existing deployments improve without operator action. Deployments that already set `COMPACTION_MODEL` or `COMPACTION_TIMEOUT_SECONDS` in the environment keep those values, since env continues to win.

Rollback is a version revert. No stored state changes shape, so a rolled-back deployment reads the same settings rows and simply ignores the new keys.

Verification is a Loki query rather than a test run: `{app="task-runner"} |= "Context compaction"` filtered by `content_manager_task_id` gives a direct before/after against a baseline of 19 failures and 0 successes.

## Open Questions

- Should the compaction call explicitly disable thinking for reasoning models (`chat_template_kwargs`, `reasoning_effort`, or a `/no_think` directive)? **Partly answered during implementation.** Run against the real proxy, `qwen3.6-35b-a3b-ud-mlx` produced a 1,248-character summary *alongside* 5,538 characters of `reasoning_content`, finishing on `stop` rather than `length`. At a 4096-token budget the thinking and the summary both fit, so disabling thinking is not required for the fix to work — it would only buy headroom. The same call took 40.4s, comfortably over the old 30s timeout, so that model was failing on both counts. Revisit only if a longer conversation pushes a reasoning model back to `finish_reason: length`, which the new diagnostic will now report.
- Should a compaction failure surface as a task event rather than only a log line? It currently degrades invisibly to the operator watching the task. This overlaps `context-usage-visibility` and is probably better placed there.
- Is `KEEP_RECENT_TOKENS = 20_000` still right once compaction works? It was never validated against a successful run, because there has not been one.
