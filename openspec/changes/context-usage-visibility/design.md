## Context

Errand reports nothing about context consumption. An operator watching a task that is misbehaving under a heavy context sees tool calls and results, but not how full the window is, how fast it is filling, or what filled it.

The investigation behind `fix-context-compaction` is the worked example: establishing that compaction had never succeeded took hand-written Loki queries, pod-label correlation and traceback reading. A single number per turn would have shown it — context climbing to the ceiling, snapping back to exactly the limit, climbing again on a roughly twelve-second cadence.

Three facts shape the design:

- `StreamEventEmitter.on_llm_end(self, context, agent, response: ModelResponse)` exists in `task-runner/main.py` and its body is `pass`. `ModelResponse.usage` carries `input_tokens`, `output_tokens`, `total_tokens` and `input_tokens_details`. Exact measurement is available for free; the estimator is not needed for reporting.
- Everything the runner writes to stderr already reaches Loki, labelled with `content_manager_task_id`. The problem is not getting data *to* Loki — it is keeping data *out of* the live view, because stderr is a single shared channel: JSON lines become typed events, everything else becomes `raw` events, and both render.
- stdout is not an escape hatch. `DockerRuntime` excludes it from the event stream, but `KubernetesRuntime` reads `read_namespaced_pod_log`, which merges stdout and stderr. A stdout-based private channel would work in development and fail in production.

## Goals / Non-Goals

**Goals:**

- Per-turn context consumption is measured exactly and visible where the operator already looks.
- Pressure is signalled when it matters, not continuously.
- Deep diagnostics reach Loki for after-the-fact analysis without appearing in the live log view.
- The measurement makes the compaction trigger point an observation rather than an assumption.

**Non-Goals:**

- Fixing compaction. That is `fix-context-compaction` and should land first; this change measures the mechanism, it does not repair it.
- Making `MAX_CONTEXT_TOKENS` model-aware or automatically tuned. This change produces the evidence for that decision; it does not take it.
- Capping tool output.
- Dumping full conversation context anywhere.

## Decisions

**Measure, don't estimate.** `response.usage.input_tokens` is the exact prompt size the provider counted. `_estimate_tokens` (`len(json.dumps(messages)) / 3`) exists to *drive* compaction and will continue to, but reporting an estimate when an exact figure is free would be a strange choice — and it would mean a badge that disagrees with the provider's own accounting. A useful side effect: the two can finally be compared, which is the only way to find out whether the heuristic driving compaction is any good.

**Report on `on_llm_end`, accept that the badge resolves late.** `input_tokens` for a turn is only known once that turn's model call returns, so the separator renders first and its badge fills in shortly after. The alternative — showing the pre-call estimate on the separator and correcting it later — trades a brief absence for a visible wrong number, which is worse. Live mode already has this shape in the "Thinking…" placeholder, so it is not a new pattern for the viewer.

**Exclude diagnostic events server-side, not client-side.** A `context_snapshot` is large by nature. Publishing it to Valkey and asking the viewer to ignore it would push the payload across the wire, into the WebSocket fan-out and into the replay buffer, where it would displace real log entries. Dropping it in `task_manager` before the publish keeps it in the pod log — and therefore Loki — while it never enters the live path at all. One control point, and the buffer stays clean.

The exclusion must cover **both** the publish and the buffer write. They are separate operations in the current code and skipping only the first would leave the payload in the replay buffer, which is the thing the exclusion exists to protect.

**Snapshot contributors by name and size, never content.** The diagnostic question is "what filled the context", and `{"tool": "execute_command", "chars": 62331}` answers it. Including the content would answer nothing extra while placing task data into Loki under its retention policy, and inflating the payload by orders of magnitude. This is a deliberate limit, not an oversight: an operator who needs the actual content has the task's tool_result events already.

**Structured events, not `logger.info`.** Production runs the task runner at `WARNING`, which is why "Context compaction triggered" has never appeared in Loki despite being logged before every attempt. `emit_event` uses `print` to stderr and bypasses log-level filtering entirely, so a structured event is delivered regardless of level. This is an independent reason to prefer events here, separate from the UI.

**Pair tokens with duration.** Context size alone does not explain a slow task; every turn re-prefills the whole context, so on local hardware latency scales with it. Emitting turn duration alongside `input_tokens` is nearly free and turns "the context is large" into "the context is large *and* each turn now costs 40 seconds", which is the actionable form. It is also what would let a future change choose the ceiling from evidence.

**Resolve the ceiling, but do not over-invest in it.** The percentage needs a denominator. `MAX_CONTEXT_TOKENS` answers "when will compaction fire"; the model's window answers "am I near overflow". They diverge sharply — gemma-4 26B reports 260,352 tokens in LM Studio against a 150,000 trigger. This change reports against the compaction trigger, because that is the threshold that actually causes behaviour today, and surfaces the raw token count so the other question remains answerable. Deriving the model's true window (via LiteLLM `/model/info` → provider `api_base` → LM Studio) is left to a later change; the plumbing is sketched in the proposal but it is a research task, not a reporting one.

## Risks / Trade-offs

**Event volume rises by one per turn** → `llm_turn_end` is a small fixed payload, roughly comparable to the existing `llm_turn_start`. Snapshots are the large ones and never reach the wire.

**An excluded event type is silently swallowed if the denylist is wrong** → The failure mode is invisible by construction, which is exactly the class of bug this codebase keeps hitting. Tests must assert both directions: excluded types are absent from the publish *and* the buffer, and non-excluded types are unaffected.

**A badge that reads 25% may imply more safety than it means** → The denominator is the compaction trigger, not the model's capacity, and on local hardware latency may bite well before either. Showing the absolute token count next to the percentage keeps the raw fact visible.

**Library and consumer bumps for the badge** → The event and Loki work need no library change and can ship first. The badge follows, and `errand-cloud` remains on `^0.11.0` and falls further behind either way.

**Snapshot payloads accumulate in Loki** → Bounded by emitting only on significant events rather than per turn, and by carrying names and sizes rather than content.

## Migration Plan

No schema, migration or stored state. New event types are additive: an older frontend receiving an unknown type renders it through the existing fallback rather than breaking, and the server-side exclusion means the largest new type never reaches a client at all.

Rollback is a version revert. Events stop being emitted; nothing that consumed them depends on their presence.

Ordering within the change matters more than usual. The runner-side emission and the server-side exclusion are independently useful — they populate Loki and answer the diagnostic question — and require no library release. The badge is the only part that needs the library loop, and it is last.

## Open Questions

- Should `context_pressure` thresholds be configurable, or are fixed values (75%, 90%) sufficient? Fixed is simpler and nothing yet suggests they need tuning.
- Should a compaction failure surface as a task event here, given it currently degrades invisibly to the operator? Raised as a follow-up in `fix-context-compaction` and arguably belongs in this change instead.
- Does the turn badge want a sparkline rather than a number? The sawtooth is the diagnostic signal, and a single number per separator shows it only if the operator reads several in sequence.
- Is there value in persisting peak context on the task record for cross-task comparison ("which tasks run hot")? That is a schema change and out of scope here, but the data would exist.
