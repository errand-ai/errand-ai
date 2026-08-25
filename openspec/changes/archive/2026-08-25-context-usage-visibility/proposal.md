## Why

Nothing in errand reports how much context a task is consuming. When a task misbehaves under a heavy context there is no way to see how full the window was, how fast it filled, or what filled it — the operator is reduced to inferring it from symptoms.

That gap has already cost real diagnostic time. Investigating repeated task stalls required hand-querying Loki, correlating pod labels, and reading tracebacks to establish something a single number per turn would have shown immediately: context climbing to the ceiling, snapping back to exactly the limit, and climbing again in a ~12-second sawtooth. See `fix-context-compaction` for that investigation.

Two things make this cheap to build now:

- `StreamEventEmitter.on_llm_end(self, context, agent, response: ModelResponse)` already exists in `task-runner/main.py` and its body is `pass`. `ModelResponse.usage` carries `input_tokens`, `output_tokens`, `total_tokens` and `input_tokens_details`. **Exact** context size is available for free — no estimation, no extra call.
- Task-runner pods are already scraped into Loki with a `content_manager_task_id` label, so per-task retrospective queries work today without new infrastructure.

Errand currently uses `_estimate_tokens` (`len(json.dumps(messages)) / 3`) to drive compaction. Nothing has ever checked that heuristic against reality; measured `input_tokens` makes that possible as a side effect.

## What Changes

- **Emit exact per-turn usage.** Fill in `on_llm_end` to emit an `llm_turn_end` event carrying `turn_id`, `input_tokens`, `output_tokens`, cached-token details and turn duration. `on_llm_start` already assigns `turn_id` and emits `llm_turn_start`, so the pairing exists.
- **Show context usage on the turn separator** in the task log view, alongside the model name it already displays:
  `Turn · gemma-4-26b-a4b-it-mlx · ctx 38.2k / 150k (25%)`
- **Warn only when it matters.** A `context_pressure` event on threshold crossings (e.g. 75%, 90%) rather than continuous noise.
- **Record diagnostic snapshots to Loki without showing them live.** On significant events only — compaction triggered, compaction failed, threshold crossed — emit a `context_snapshot` carrying message count and the largest contributors *by tool name and size, not content*. The server drops this event type before publishing to Valkey, so it reaches the pod log (and therefore Loki) but never the live view or the replay buffer.
- Resolve the ceiling the percentage is measured against, rather than assuming the hard-coded 150,000.

**Not in scope**: fixing compaction. That is `fix-context-compaction`, which should land first — this change measures the mechanism, it does not repair it.

## Capabilities

### New Capabilities

- `task-context-telemetry`: per-turn context measurement, threshold events, and the diagnostic snapshot channel that reaches Loki without reaching the live log view.

### Modified Capabilities

- `structured-task-events`: add `llm_turn_end`, `context_pressure` and `context_snapshot` to the event protocol table, and modify the Valkey message format requirement so that designated event types are deliberately not forwarded — dropped from both the live publish and the replay buffer.

The exclusion belongs in `structured-task-events`, which owns the publish path, not `live-task-log-streaming`, which covers only the viewer modal. Note the protocol table is already missing `llm_turn_start`, which the runner emits today; this change documents it alongside its new counterpart.

## Impact

- **Code**: `task-runner/main.py` (`on_llm_end`, snapshot emission), `errand/task_manager.py` (event-type denylist before publish and buffer write), plus a resolved ceiling passed to the runner.
- **Library dependency**: the turn separator is `TurnGroupView.vue` in `@errand-ai/ui-components`, so the badge requires a library release and a consumer bump in `errand`. `errand-cloud` is still on `^0.11.0` and would fall further behind. The event emission and the Loki path need no library change and can ship first.
- **Design note — ordering**: `input_tokens` for a turn is only known once that turn's model call returns, so the separator renders first and its badge resolves shortly after. This mirrors the existing "Thinking…" placeholder and is not a new pattern.
- **Design note — which ceiling**: capability and latency give different answers. Gemma-4 26B reports a 260,352-token window in LM Studio, but every turn re-prefills the whole context, so on local hardware the binding constraint is latency, not capacity. Percentage against the compaction trigger answers "when will compaction fire"; percentage against the model window answers "am I near overflow". Pairing `input_tokens` with turn duration is what makes the right ceiling an observation rather than a guess.
- **Privacy**: snapshots deliberately carry tool names and sizes, never message content. A full context dump would place task data in Loki under its retention policy.
- **Production log level**: the runner runs at `WARNING`, so `logger.info` diagnostics are silently dropped. `emit_event` uses `print` to stderr and bypasses log-level filtering, which is an independent reason to prefer structured events here.
