## 1. Branch and version

- [ ] 1.1 Confirm `fix-context-compaction` has merged first — this change measures the compaction mechanism and its thresholds, and measuring a mechanism that never succeeds produces a misleading baseline
- [ ] 1.2 Create branch `context-usage-visibility` from an up-to-date `main`
- [ ] 1.3 Bump `VERSION` (minor — new events and task log display)

## 2. Runner: measure the turn

Groups 2 and 3 deliver the diagnostic value on their own. Neither needs a library release, and together they populate Loki and answer "what filled the context" — the badge in group 5 is presentation on top.

- [ ] 2.1 Write failing tests first: `llm_turn_end` carries the same `turn_id` as its `llm_turn_start`, reports provider usage rather than the internal estimate, and includes turn duration
- [ ] 2.2 Write a failing test for the degenerate case: a response with no usage information completes the turn with token fields omitted, rather than raising
- [ ] 2.3 Fill in `on_llm_end` to emit `llm_turn_end` from `response.usage` — the hook already exists with an empty body and the correct signature
- [ ] 2.4 Confirm the emitted value is the provider's count, not `_estimate_tokens`. Reporting the estimate would put a number on screen that disagrees with the provider's own accounting
- [ ] 2.5 Record how far `_estimate_tokens` diverges from the measured figure on a real task. The estimate drives compaction and has never been checked against reality; if it is badly wrong, that belongs in a follow-up rather than this change

## 3. Runner: pressure and snapshots

- [ ] 3.1 Write failing tests for `context_pressure`: emitted once on a crossing, not re-emitted while merely remaining above a threshold, silent below all thresholds
- [ ] 3.2 Implement threshold crossing detection and emit `context_pressure`
- [ ] 3.3 Write failing tests for `context_snapshot`: emitted on compaction and on threshold crossings but never per turn; contributors carry role, tool name and size; **no message content appears in the payload**
- [ ] 3.4 Implement snapshot emission with contributors ranked by size
- [ ] 3.5 Confirm snapshots use `emit_event`, not `logger.info` — production runs the runner at `WARNING`, which is why "Context compaction triggered" has never appeared in Loki

## 4. Server: keep snapshots out of the live view

- [ ] 4.1 Write failing tests asserting **both** directions: an excluded type is absent from the Valkey publish and absent from the replay buffer, and a non-excluded type is published and buffered exactly as before
- [ ] 4.2 Add the excluded-type set and apply it in `task_manager` before publishing
- [ ] 4.3 Apply it to the buffer write as well — publish and buffer are separate operations, and excluding only the publish leaves the payload in the replay buffer, which is what the exclusion exists to protect
- [ ] 4.4 Confirm excluded events still reach the container log, and therefore Loki, by querying `{app="task-runner"} |= "context_snapshot"` filtered by `content_manager_task_id`
- [ ] 4.5 Confirm no regression in the live view: existing event types render as before

## 5. Library: the turn badge

Requires a `@errand-ai/ui-components` release and a consumer bump. Everything above ships without it.

- [ ] 5.1 In the library, handle `llm_turn_end` and attach usage to the matching turn group by `turn_id`
- [ ] 5.2 Render usage on the turn separator in `TurnGroupView.vue` alongside the model name, showing the absolute token count and not a percentage alone
- [ ] 5.3 Confirm a turn with no `llm_turn_end` renders exactly as today — no placeholder number, no error
- [ ] 5.4 Release the library, then bump the pin in `errand`
- [ ] 5.5 Note `errand-cloud` remains on `^0.11.0` and falls further behind; out of scope here but worth recording

## 6. Verify

- [ ] 6.1 Backend, task-runner and frontend suites green
- [ ] 6.2 Run a task heavy enough to trigger compaction and confirm the turn badges show context climbing across turns
- [ ] 6.3 Confirm no `context_snapshot` appears anywhere in the live Task Logs view
- [ ] 6.4 Confirm the same snapshots are retrievable from Loki for that task
- [ ] 6.5 Compare the sequence of `input_tokens` values against the compaction trigger. The sawtooth this exposes — context climbing, snapping back, climbing again — is the signal the whole change exists to make visible

## 7. Follow-ups (not this change)

- [ ] 7.1 Decide the right ceiling from the collected evidence. Capability and latency give different answers: gemma-4 26B reports a 260,352-token window against a 150,000 trigger, while every turn re-prefills the whole context so latency binds first on local hardware
- [ ] 7.2 Resolve a model's true window via LiteLLM `/model/info` → provider `api_base` → LM Studio's `max_context_length`. Note `errand/model_metadata.py` already downloads `model_prices_and_context_window.json` and reads only two fields from it
- [ ] 7.3 Consider persisting peak context on the task record for cross-task comparison — a schema change, but the data would exist
- [ ] 7.4 Consider whether a compaction failure should surface as a task event; it currently degrades invisibly to the operator watching the task
