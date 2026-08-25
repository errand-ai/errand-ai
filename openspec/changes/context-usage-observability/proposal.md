## Why

`context-usage-visibility` (#239) made context pressure measurable, but it made it measurable in Loki. An operator watching a task in the UI still cannot see how close it is to its ceiling, cannot compare one task against another, and cannot see that its compaction failed.

The data now exists in the event stream; what is missing is somewhere for it to land and someone to show it to. This change closes that gap without touching how the measurement is taken.

## What Changes

- **Persist peak context on the task record.** Every task now emits `input_tokens` per turn, but the series lives only in the event stream and the container log, so nothing survives for cross-task comparison. Recording the peak (and the ceiling in force at the time, since it is configurable) makes "which of our workloads run hot" answerable without a Loki query. Requires a schema change.
- **Surface compaction failure as a task event.** A failed compaction currently emits a `context_snapshot` with `reason: compaction_failed`, which is deliberately excluded from the live path — so it reaches Loki and the container log, but never the operator watching the task. The task degrades to trimming and looks healthy. A distinct, live-visible event for the failure (carrying the reason, not the payload) makes it observable where the operator already is.
- **Add a settings-UI card for `max_context_tokens`.** The setting and its plumbing shipped with #239 but no card was built, so the ceiling is API- and env-only today. This is the value the pressure thresholds are measured against; it should be adjustable where every other operational setting is.

## Capabilities

### New Capabilities

<!-- None. Each item extends an existing surface. -->

### Modified Capabilities

- `task-api`: the task record and its response gain a peak-context field; consumers can read it without replaying events.
- `structured-task-events`: a compaction failure becomes a first-class task event rather than an excluded diagnostic, so it reaches the live view.
- `admin-settings-ui`: `max_context_tokens` gains a card, making the context ceiling operator-adjustable.
- `settings-registry`: registration for the new card, if not already covered by #239's registry entry.

## Impact

- `errand/models.py` + an Alembic migration for the peak-context column; `errand/task_manager.py` to record it from the event stream.
- `errand/task_manager.py` — `LIVE_EXCLUDED_EVENT_TYPES` stays as it is; the new failure event is a separate, small payload rather than an unexclusion of `context_snapshot`. That distinction matters: the snapshot was excluded because it is large and would displace real entries in the bounded replay buffer, and that reasoning still holds.
- `frontend/` — a settings card, and whatever surfaces peak context on the task view.
- Depends on nothing in `context-accounting-correctness`, but note that change alters *when* compaction fires, so the two touching production close together will make the peak-context numbers before and after non-comparable.
