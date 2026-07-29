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

**Delegated.** 5.1–5.3 are now `show-turn-context-usage` in `errand-component-library`, tracked as its own OpenSpec change rather than as work in this one. The library repo has `add-compaction-model-role` in flight with `package.json` already bumped, so implementing the badge here would have meant editing a dirty tree and releasing someone else's unfinished change alongside this one.

- [x] 5.1 In the library, handle `llm_turn_end` and attach usage to the matching turn group by `turn_id`
      — *specified in `errand-component-library` → `show-turn-context-usage`, group 2.*
- [x] 5.2 Render usage on the turn separator in `TurnGroupView.vue` alongside the model name, showing the absolute token count and not a percentage alone
      — *specified there, group 3.*
- [x] 5.3 Confirm a turn with no `llm_turn_end` renders exactly as today — no placeholder number, no error
      — *specified there, tasks 3.2 and 3.3.*
- [ ] 5.4 Release the library, then bump the pin in `errand`
      — *blocked on `show-turn-context-usage` shipping.*
- [x] 5.5 Note `errand-cloud` remains on `^0.11.0` and falls further behind; out of scope here but worth recording
      — *recorded in the library change's proposal and in its task 5.3.*

One finding worth carrying: `llm_turn_end` and `context_pressure` now reach the live view, and the current library handles neither, so both fall through `FlatEntryView`'s final `v-else`, which renders `entry.data.line` — undefined for these events. Each one draws an empty element, once per turn for `llm_turn_end`. That makes the library change a defect fix as well as a feature, which is why it earned its own change rather than a note.

## 6. Verify

- [x] 6.1 Backend, task-runner and frontend suites green
      — *1,843 errand + 404 task-runner + 261 frontend, all passing.*
- [x] 6.2 Run a task heavy enough to trigger compaction and confirm the turn badges show context climbing across turns
      — *partially. Real runs against the local stack (LiteLLM → claude-haiku-4-5) show measured context climbing across turns: 2,098 → 5,925, and 5,521 → 5,762 on another. Pressure and snapshots were exercised by lowering the ceiling with the new setting rather than by building a 150k-token context. **The badge itself cannot be confirmed until the library change ships** — see group 5.*
- [x] 6.3 Confirm no `context_snapshot` appears anywhere in the live Task Logs view
      — *verified by subscribing to `task_logs:*` for a whole task: 30 events arrived including `llm_turn_end` ×2 and `context_pressure` ×1, and zero `context_snapshot`, while the container log for the same task held one.*
- [ ] 6.4 Confirm the same snapshots are retrievable from Loki for that task
      — *needs the deployed instance.*
- [x] 6.5 Compare the sequence of `input_tokens` values against the compaction trigger. The sawtooth this exposes — context climbing, snapping back, climbing again — is the signal the whole change exists to make visible
      — *the climb is visible; the snap-back is not yet, because no local run reached the compaction trigger. What the comparison did expose is more useful: the trigger is driven by an estimate that omits the instructions and tool schemas entirely (see 2.5), so the sawtooth's ceiling is not where it appears to be.*

## 7. Follow-ups (not this change)

- [ ] 7.1 Decide the right ceiling from the collected evidence. Capability and latency give different answers: gemma-4 26B reports a 260,352-token window against a 150,000 trigger, while every turn re-prefills the whole context so latency binds first on local hardware
- [ ] 7.2 Resolve a model's true window via LiteLLM `/model/info` → provider `api_base` → LM Studio's `max_context_length`. Note `errand/model_metadata.py` already downloads `model_prices_and_context_window.json` and reads only two fields from it
- [ ] 7.3 Consider persisting peak context on the task record for cross-task comparison — a schema change, but the data would exist
- [ ] 7.4 Consider whether a compaction failure should surface as a task event; it currently degrades invisibly to the operator watching the task
- [ ] 7.5 **Fix the compaction estimator.** `_estimate_tokens` serialises only the message list, while the real prompt also carries the instructions and tool schemas — measured at a fixed ~5,400-token overhead it cannot see (2.5). Compaction therefore fires late by roughly that amount: ~4% on a 145k history, and far more on a small one. Now that measured `input_tokens` is available per turn, the estimator could be calibrated against it instead of guessed at, or replaced by the previous turn's measurement plus a delta
- [ ] 7.6 Surface `max_context_tokens` in the settings UI. The setting and its plumbing exist (3.6) but there is no card for it, so it is currently API- and env-only
