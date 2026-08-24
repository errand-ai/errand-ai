## 1. Branch and version

- [x] 1.1 Confirm `fix-context-compaction` has merged first — this change measures the compaction mechanism and its thresholds, and measuring a mechanism that never succeeds produces a misleading baseline
- [x] 1.2 Create branch `context-usage-visibility` from an up-to-date `main`
- [x] 1.3 Bump `VERSION` (minor — new events and task log display)

## 2. Runner: measure the turn

Groups 2 and 3 deliver the diagnostic value on their own. Neither needs a library release, and together they populate Loki and answer "what filled the context" — the badge in group 5 is presentation on top.

- [x] 2.1 Write failing tests first: `llm_turn_end` carries the same `turn_id` as its `llm_turn_start`, reports provider usage rather than the internal estimate, and includes turn duration
- [x] 2.2 Write a failing test for the degenerate case: a response with no usage information completes the turn with token fields omitted, rather than raising
- [x] 2.3 Fill in `on_llm_end` to emit `llm_turn_end` from `response.usage` — the hook already exists with an empty body and the correct signature
- [x] 2.4 Confirm the emitted value is the provider's count, not `_estimate_tokens`. Reporting the estimate would put a number on screen that disagrees with the provider's own accounting
- [x] 2.5 Record how far `_estimate_tokens` diverges from the measured figure on a real task. The estimate drives compaction and has never been checked against reality; if it is badly wrong, that belongs in a follow-up rather than this change
      — **Measured on a real run: estimate 501 tokens against a measured 5,925. The estimate is 8.5% of the truth.** The cause is structural, not a bad ratio: `_estimate_tokens` serialises only the message list, while `input_tokens` also counts the instructions and tool schemas, which are passed separately and never seen by the estimator. The gap is a roughly fixed ~5,400-token overhead, so it dominates a small context and shrinks proportionally as messages grow — on a 145k-token message history it understates by about 4%, meaning compaction fires slightly *late* rather than never. Real, bounded, and a follow-up as this task anticipated. See 7.5.

- [x] 2.6 **(added)** Ask the provider for usage at all. The first real run reported `input_tokens: 0` on every turn: the agent SDK sets `stream_options.include_usage` only when the client points at OpenAI's own endpoint, and errand's points at LiteLLM, so the streaming usage chunk was never requested. Fixed with `include_usage=True` on `ModelSettings`; re-verified on a real run, which then reported 5,521 → 5,762 across two turns
- [x] 2.7 **(added)** Treat a usage block of zeros as no measurement rather than a measurement of zero — otherwise the badge shows a confident `0`. A zero prompt is impossible for a real turn

## 3. Runner: pressure and snapshots

- [x] 3.1 Write failing tests for `context_pressure`: emitted once on a crossing, not re-emitted while merely remaining above a threshold, silent below all thresholds
- [x] 3.2 Implement threshold crossing detection and emit `context_pressure`
- [x] 3.3 Write failing tests for `context_snapshot`: emitted on compaction and on threshold crossings but never per turn; contributors carry role, tool name and size; **no message content appears in the payload**
- [x] 3.4 Implement snapshot emission with contributors ranked by size
- [x] 3.5 Confirm snapshots use `emit_event`, not `logger.info` — production runs the runner at `WARNING`, which is why "Context compaction triggered" has never appeared in Loki
- [x] 3.6 **(added)** Make the ceiling settable. `MAX_CONTEXT_TOKENS` was read from the runner's own environment with a hard-coded 150,000 default and was never set by the server, so the denominator the thresholds are measured against could not be configured at all. Added a `max_context_tokens` setting resolved and forwarded like `compaction_max_tokens`. The proposal's Impact called for "a resolved ceiling passed to the runner"; no task had covered it
- [x] 3.7 **(added)** Add the key to `_read_settings`' select list, not just the forwarding. Forwarding it without loading it produced a setting that silently did nothing — found on a real run where the runner kept measuring against 150,000. Covered by a loader-level test, since the injection tests pass `settings` in directly and cannot catch this

## 4. Server: keep snapshots out of the live view

- [x] 4.1 Write failing tests asserting **both** directions: an excluded type is absent from the Valkey publish and absent from the replay buffer, and a non-excluded type is published and buffered exactly as before
- [x] 4.2 Add the excluded-type set and apply it in `task_manager` before publishing
- [x] 4.3 Apply it to the buffer write as well — publish and buffer are separate operations, and excluding only the publish leaves the payload in the replay buffer, which is what the exclusion exists to protect
      — *`_live_log_message` returns `None` for excluded types and both operations derive from that one value, so an excluded event cannot reach one of them by omission.*
- [x] 4.4 Confirm excluded events still reach the container log, and therefore Loki, by querying `{app="task-runner"} |= "context_snapshot"` filtered by `content_manager_task_id`
      — *verified locally rather than via Loki: on one real task the container log held `context_snapshot: 1` while the Valkey channel held none. The Loki query itself needs the deployed instance and is left to 6.4.*
- [x] 4.5 Confirm no regression in the live view: existing event types render as before
      — *existing `test_worker.py` publish tests still pass. Note the new types are not regression-free on the **current** library: `llm_turn_end` falls through `FlatEntryView`'s final `v-else`, which renders `entry.data.line` — undefined here — so it draws an empty element per turn until 5.1 consumes it.*

## 5. Library: the turn badge

Requires a `@errand-ai/ui-components` release and a consumer bump. Everything above ships without it.

**Delegated, and now landed.** 5.1–5.3 became `show-turn-context-usage` in `errand-component-library`, tracked as its own OpenSpec change rather than as work in this one — that repo had `add-compaction-model-role` in flight with `package.json` already bumped, so implementing the badge here would have meant editing a dirty tree and releasing someone else's unfinished change alongside this one. Both changes have since shipped and archived; v0.18.0 carries the badge, and the pin is bumped in this branch.

- [x] 5.1 In the library, handle `llm_turn_end` and attach usage to the matching turn group by `turn_id`
      — *specified in `errand-component-library` → `show-turn-context-usage`, group 2.*
- [x] 5.2 Render usage on the turn separator in `TurnGroupView.vue` alongside the model name, showing the absolute token count and not a percentage alone
      — *specified there, group 3.*
- [x] 5.3 Confirm a turn with no `llm_turn_end` renders exactly as today — no placeholder number, no error
      — *specified there, tasks 3.2 and 3.3.*
- [x] 5.4 Release the library, then bump the pin in `errand`
      — *`@errand-ai/ui-components` 0.16.0 → 0.18.0. Verified against the real published component rather than trusting the pin: a new integration test mounts `TaskLogViewer` from the installed package and feeds it a log stream captured verbatim from a real task, asserting the badge text. The separator renders `Turn · claude-haiku-4-5-20251001 · 5.5k tokens · 3.3s`, then `5.9k tokens · 2.0s` — the climb, visible.*
      — *That test guards the seam between the two repos, which neither repo's own suite can see: the library tests its rendering against fixtures it wrote, and errand tests its emission against fixtures it wrote. Whether the fields one emits are the fields the other reads is only checked here.*
- [x] 5.5 Note `errand-cloud` remains on `^0.11.0` and falls further behind; out of scope here but worth recording
      — *recorded in the library change's proposal and in its task 5.3.*

One finding worth carrying, now resolved: `llm_turn_end` and `context_pressure` reach the live view, and the library at 0.16.0 handled neither, so both fell through `FlatEntryView`'s final `v-else`, which renders `entry.data.line` — undefined for these events. Each drew an empty element, once per turn for `llm_turn_end`. That made the library change a defect fix as well as a feature, which is why it earned its own change rather than a note. 0.18.0 consumes both, and a regression test asserts `llm_turn_end` produces no rendered entry.

## 6. Verify

- [x] 6.1 Backend, task-runner and frontend suites green
      — *1,845 errand + 404 task-runner + 38 evals + 267 frontend, all passing.*
- [x] 6.2 Run a task heavy enough to trigger compaction and confirm the turn badges show context climbing across turns
      — *the badges show the climb: `5.5k tokens · 3.3s` then `5.9k tokens · 2.0s`, rendered by the released component from a real task's events. No local run reached the 150k compaction trigger, so pressure and snapshots were exercised by lowering the ceiling through the new setting instead — which is a fair substitute for the thresholds but leaves compaction's own behaviour under a genuinely large context unobserved.*
- [x] 6.3 Confirm no `context_snapshot` appears anywhere in the live Task Logs view
      — *verified by subscribing to `task_logs:*` for a whole task: 30 events arrived including `llm_turn_end` ×2 and `context_pressure` ×1, and zero `context_snapshot`, while the container log for the same task held one.*
- [x] 6.4 Confirm the same snapshots are retrievable from Loki for that task
      — *confirmed on the deployed instance, which runs this branch: both `errand-server` and `TASK_RUNNER_IMAGE` are on `0.145.0-pr239.1090`, the image built from tip `0df1e1e` (run 30502195289, `run_number` 1090). The local task from 6.3 never shipped to Loki, so the check was made against a deployed task instead.*
      — *`{namespace="errand", container="task-runner"} |= "context_snapshot"` returns entries over the last 7 days, labelled per task by `content_manager_task_id`. Task `ca6c6bb8-192a-41d6-b2c5-746f83e76743` (2026-08-21T12:14:49Z) carries the pair the change exists to produce, 7ms apart: `context_pressure` at `input_tokens 112503 / limit 150000 / threshold 0.75`, then the `threshold_crossed` snapshot naming what filled it — `recall` 57,104 chars, three `web_search` results at ~20k each, `read_file` 17,155 — with `input_tokens 112503` beside `estimated_tokens 134194`. Sizes and tool names only; no content.*
      — *This closes the round trip. The snapshot is absent from the live path (6.3) and present in Loki, which is exactly the split `LIVE_EXCLUDED_EVENT_TYPES` was written for.*
      — *A 30-day sweep of the trigger itself: 8 tasks reached it, `073c32df` (7 triggers), `08ca7845` (10), `21a4bdc4` (32), `2ece82fc` (41), `765c3872` (2), `8114ff66` (14), `b9679638` (39), `db9b2dd7` (32). Three of those ran under this branch's image and emitted `compaction_triggered` snapshots 1:1 with the warning; the five from 2026-07-30 predate the deploy and logged the warning alone, which dates the rollout between 07-30 and 08-05.*
      — *The measured ceiling has never been breached. Peak `input_tokens` across all 216 tasks reporting turn usage is 142,623 on `765c3872` — 95.1% of the 150,000 limit — then 126,149, 121,078, 120,166, 117,046. Compaction is holding.*
      — *Reading the two numbers together corrects a tempting misreading of the snapshots. `estimated_tokens` climbs monotonically within a task — `b9679638` went 337,040 -> 589,171 across 39 triggers as its message count went 71 -> 290 — which looks like compaction failing to reclaim anything. It is not. The SDK discards `call_model_input_filter` output and rebuilds history from the run loop's own items, so `_compact_context` is handed the full uncompacted list every turn and `estimated_before` is its input, never its result. The same task's measured prompt peaked at 126,149. `estimated_tokens` in a snapshot is the pre-compaction history, `input_tokens` is what actually reached the model, and only the second is a statement about context pressure.*
      — *What the snapshots do expose is a single `read_file` result of 908,499 chars pinned at the top of `top_contributors` on every one of `b9679638`'s snapshots. It never reaches the model, but it is re-summarised from scratch every turn, and that task is also the one with three `compaction_failed` events and backoff to 4 turns — consistent with a summarisation call that cannot swallow a ~227k-token message. Worth a follow-up: cap a tool result at ingest. Distinct from 7.5, which is about the estimator's fixed blind spot, not about one oversized message.*
- [x] 6.5 Compare the sequence of `input_tokens` values against the compaction trigger. The sawtooth this exposes — context climbing, snapping back, climbing again — is the signal the whole change exists to make visible
      — *the climb is visible; the snap-back is not yet, because no local run reached the compaction trigger. What the comparison did expose is more useful: the trigger is driven by an estimate that omits the instructions and tool schemas entirely (see 2.5), so the sawtooth's ceiling is not where it appears to be.*
      — *Superseded by production data while verifying 6.4. The sawtooth is fully visible in the measured series for task `b9679638` on 2026-08-11/12 (pod `task-runner-177a9f0c`), three teeth over ~2h40m of `input_tokens`: a climb 32,597 -> 37,763 to a peak of **126,149** at 23:45, snapping to **13,940** by 00:00; a second climb to **72,256** by 00:50, snapping to **24,218** at 00:55; a third climb through 95,036 to 110,854 at 01:45. The snap-backs align with the compaction warnings logged at 23:52 and 00:01. This is the signal the change exists to make visible, and it is now observable in Loki without instrumenting anything further.*

## 7. Follow-ups (not this change)

- [ ] 7.1 Decide the right ceiling from the collected evidence. Capability and latency give different answers: gemma-4 26B reports a 260,352-token window against a 150,000 trigger, while every turn re-prefills the whole context so latency binds first on local hardware
- [ ] 7.2 Resolve a model's true window via LiteLLM `/model/info` → provider `api_base` → LM Studio's `max_context_length`. Note `errand/model_metadata.py` already downloads `model_prices_and_context_window.json` and reads only two fields from it
- [ ] 7.3 Consider persisting peak context on the task record for cross-task comparison — a schema change, but the data would exist
- [ ] 7.4 Consider whether a compaction failure should surface as a task event; it currently degrades invisibly to the operator watching the task
- [ ] 7.5 **Fix the compaction estimator.** `_estimate_tokens` serialises only the message list, while the real prompt also carries the instructions and tool schemas — measured at a fixed ~5,400-token overhead it cannot see (2.5). Compaction therefore fires late by roughly that amount: ~4% on a 145k history, and far more on a small one. Now that measured `input_tokens` is available per turn, the estimator could be calibrated against it instead of guessed at, or replaced by the previous turn's measurement plus a delta
- [ ] 7.6 Surface `max_context_tokens` in the settings UI. The setting and its plumbing exist (3.6) but there is no card for it, so it is currently API- and env-only
- [ ] 7.7 **Cap a tool result at ingest.** Task `b9679638` carried a single `read_file` result of 908,499 chars — roughly 227k tokens, more than the whole 150,000 context ceiling — pinned at the top of `top_contributors` on all 39 of its snapshots. It never reaches the model, because compaction summarises it away every turn, but that is the cost: the summariser is handed a message larger than its own window on every one of those turns, and this is the task with three `compaction_failed` events and backoff widening to 4 turns. The measured prompt still peaked at a safe 126,149, so this degrades rather than breaks — the fallback trim covers it. Distinct from 7.5: that is the estimator's fixed blind spot on an ordinary history, this is one message no summariser can swallow. A cap at the point the tool result enters the message list (truncate with a marker naming the elided size) bounds the problem where it starts, rather than asking compaction to absorb it repeatedly
