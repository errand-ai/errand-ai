## 1. Branch and version

- [x] 1.1 Create branch `fix-context-compaction` from an up-to-date `main`
- [x] 1.2 Bump `VERSION` (minor — new operator settings and changed runtime behaviour)

## 2. Runner: make the compaction call survivable

These four are the fix. None requires a server, settings or library change, so this group can be verified on its own against the current 0-success baseline.

- [x] 2.1 Write failing tests first: compaction timeout and `max_tokens` read from env with documented defaults; invalid values fall back with a warning; `LLM_REQUEST_TIMEOUT` does not affect the compaction timeout
- [x] 2.2 Raise the default compaction timeout from 30s and read `COMPACTION_MAX_TOKENS`, defaulting above 2048 — 30s cannot cover 2048 tokens of generation on a local or free-tier model
- [x] 2.3 Write failing tests for the empty-summary diagnostic: finish reason, content length, and presence of a reasoning/thinking field are all reported, at `WARNING` so production's log level does not discard them
- [x] 2.4 Emit that diagnostic on the empty-summary path — this is what distinguishes "model declined" from "thinking consumed the budget", and neither is currently visible

## 3. Runner: stop the per-turn tax

- [x] 3.1 Write failing tests for trim headroom: a trim from over-limit lands materially below `MAX_CONTEXT_TOKENS`, and a following turn of typical size does not immediately re-cross it
- [x] 3.2 Change `_trim_context_window` to trim to a target below the ceiling rather than stopping at it
- [x] 3.3 Write failing tests for backoff: consecutive failures widen the suppression window; suppressed turns make no summarization call; a success resets the count; total calls stay bounded when every attempt fails
- [x] 3.4 Add the backoff state and wire it into `_compact_context`, logging entry and reset at `WARNING`
- [x] 3.5 Confirm the interaction: with compaction suppressed, trimming still keeps the task running rather than stalling

## 4. Server: settings resolution

- [x] 4.1 Write failing tests for the three registry keys, including env-over-DB-over-default resolution and rejection of a non-positive timeout
- [x] 4.2 Register `compaction_model`, `compaction_timeout`, `compaction_max_tokens` in `settings_registry`
- [x] 4.3 Add `compaction_model` to `MODEL_SETTING_KEYS` — **not optional**: without it the settings card writes `model_id`, the backend reads `model`, and the resolved model is an empty string. This is the defect fixed in `selective-mcp-server-defaults`, and the test in 4.4 is what stops it recurring
- [x] 4.4 Write a failing test that a `compaction_model` written as `{provider_id, model_id}` resolves to a non-empty model name
- [x] 4.5 Inject the three resolved values into the runner environment from `task_manager`, alongside the existing `LLM_REQUEST_TIMEOUT` injection
- [x] 4.6 Confirm env vars still override the settings, so deployments already setting `COMPACTION_MODEL` are unaffected

## 5. Verify locally

- [x] 5.1 Full backend suite green
- [x] 5.2 Task-runner suite green
- [x] 5.3 Drive a compaction end-to-end against a real model and confirm a summary is produced — the first successful compaction in the recorded history of this mechanism, so do not treat "no error" as success; confirm the summary message is present in the conversation
- [x] 5.4 Force a compaction failure and confirm backoff engages, the suppression is logged, and the task continues on trimmed context rather than stalling — covered by six unit tests (suppression, widening window, reset on success, bounded attempts, suppressed turns still trim, WARNING on entry). Not exercised end-to-end locally: that needs a task heavy enough to trigger compaction against a deliberately broken model, and belongs with the deployed verification in 6.4/6.5
- [x] 5.5 Confirm the settings are writable via `PUT /api/settings` and take effect in a subsequent task, without any UI

## 6. Ship

- [x] 6.1 Commit, push, open a PR
- [x] 6.2 Confirm CI is green
- [ ] 6.3 Deploy to Kubernetes and confirm pod health
- [ ] 6.4 Run a task heavy enough to trigger compaction, then query Loki: `{app="task-runner"} |= "Context compaction"` filtered by `content_manager_task_id`. Baseline is 19 failures / 0 successes over 14 days — anything other than a success here means the change did not work
- [ ] 6.5 If compaction still fails, read the new empty-summary diagnostic before changing anything: it identifies which lever to pull, and guessing is what this change exists to stop
- [ ] 6.6 Merge, delete the branch

## 7. Follow-ups (not this change)

- [ ] 7.1 Expose the three settings on the Task Management tab. Requires a `TaskManagementCard` change in `@errand-ai/ui-components`, a release, and a consumer bump — the settings work via the API without it, which is why it is separated
- [ ] 7.2 Decide whether to disable thinking for compaction calls on reasoning models. The diagnostic from 2.4 should decide this rather than guesswork
- [ ] 7.3 Revisit `KEEP_RECENT_TOKENS = 20_000`, never validated against a successful compaction because there has not been one
- [ ] 7.4 Consider whether compaction failure should surface as a task event, not only a log line — likely belongs in `context-usage-visibility`
