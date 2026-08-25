## Context

`context-usage-visibility` (#239) made context consumption measurable. It made it measurable *in Loki*. Every claim in this session about production context behaviour — the 142,623-token peak, the eight tasks that reached the compaction trigger, the sawtooth — required a LogQL query to establish. None of it is visible to an operator looking at a task, and none of it survives log retention.

Three specific gaps follow from that:

- **No durable record.** `input_tokens` exists per turn in the event stream and the container log. Nothing persists, so "which of our workloads run hot" cannot be answered from the database, and cannot be answered at all once logs age out.
- **A failure that looks like health.** When compaction fails, the runner emits a `context_snapshot` with `reason: compaction_failed` and falls back to trimming. That snapshot is deliberately excluded from the live path, so the operator watching the task sees a task proceeding normally. Production shows one task failing compaction three times and backing off to a 4-turn suppression window, entirely invisibly.
- **A ceiling nobody can reach.** `max_context_tokens` shipped with its plumbing but no settings card, so the value every pressure threshold is measured against is API- and env-only.

## Goals / Non-Goals

**Goals:**

- Persist enough per-task context data to compare tasks without a log query, and to keep the comparison after logs expire.
- Make a compaction failure visible where the operator already is, without weakening the reason `context_snapshot` is excluded from that path.
- Give `max_context_tokens` a settings card alongside the compaction settings it belongs with.

**Non-Goals:**

- Changing what is measured or how. The event stream from #239 is the input; this change only routes and stores it.
- Changing when compaction fires. That is `context-accounting-correctness`, and the two interact — see Risks.
- Deciding the right ceiling value. That is `context-ceiling-research`.
- Unexcluding `context_snapshot` from the live path.

## Decisions

### 1. A new small event for the failure, not an exception to the exclusion

**Chosen:** emit a distinct, small event carrying the failure reason and the consecutive-failure count, and let it through the live path. Leave `context_snapshot` excluded exactly as it is.

**Why:** the exclusion was not a blanket judgement about diagnostics being uninteresting. `LIVE_EXCLUDED_EVENT_TYPES` exists because snapshots are large and would displace real entries in the bounded replay buffer — the comment in `task_manager.py` says so, and that reasoning is untouched by wanting failures visible. Carving an exception for `reason: compaction_failed` would mean the exclusion depends on payload contents rather than event type, so the filter would have to parse and branch on `data`, and the large `top_contributors` array would ride along anyway. A separate event costs one event type and keeps the filter a set-membership test.

**Alternatives considered:**

- *Unexclude `context_snapshot` when `reason == "compaction_failed"`.* Reuses an existing type, but puts the full contributor array into the replay buffer at exactly the moment the task is in trouble and the buffer is most valuable.
- *Surface it from the server by watching for the snapshot in the log stream.* Server-side inference from a stream it is already filtering; more moving parts, same result.

### 2. Persist peak plus the ceiling in force, not peak alone

**Chosen:** record both the peak `input_tokens` and the `max_context_tokens` value in effect for that task.

**Why:** the ceiling is configurable and `context-ceiling-research` may well change it. A bare peak of 126,149 means something different against a 150,000 ceiling than against 260,352, and a stored series of peaks with no denominator becomes uninterpretable the moment the setting moves. Storing both makes the ratio computable after the fact, which is the number anyone actually wants.

**Alternatives considered:**

- *Peak only.* Smaller, and wrong as soon as the ceiling changes.
- *The full per-turn series.* Complete, but it is a per-task table for data that already exists in Loki for its useful lifetime. The peak is what survives being worth keeping.

### 3. Record from the event stream the server already parses

**Chosen:** capture the peak in `task_manager.py` where `llm_turn_end` is already being read for the live path, and write it on task completion rather than per turn.

**Why:** the parse already happens; the value is one comparison. Writing per turn would mean a database write per model call for a value only read after the fact.

**Trade-off to accept:** a task that dies without completing loses its peak. Given the value is for cross-task comparison rather than live monitoring, and that a crashed task's context data is still in Loki for its retention window, that is the right side of the trade. Worth revisiting if crashed tasks turn out to be exactly the ones worth comparing.

### 4. `max_context_tokens` joins the existing compaction settings card

**Chosen:** add it to the compaction settings group rather than creating a new card.

**Why:** `settings-registry` already specifies a Compaction settings requirement covering `compaction_model`, `compaction_timeout` and `compaction_max_tokens`. `max_context_tokens` is the trigger those three respond to; separating them would put the threshold and its handling on different screens. The registry entry already exists (`errand/settings_registry.py`), so this is UI work, not plumbing.

## Risks / Trade-offs

- **Landing near `context-accounting-correctness` makes the peak series non-comparable across the boundary** → That change alters when compaction fires, so peaks recorded before and after describe different systems. Sequence them deliberately and record which change was live when a peak was captured; the stored ceiling helps but does not capture this. If both land in the same window, treat the pre-change baseline as closed rather than continuous.
- **A migration for a column that may be superseded** → If `context-ceiling-research` concludes the ceiling should be per-model, the stored ceiling becomes a resolved value rather than a global setting. The column still holds the right thing (what was in force for that task); only its provenance changes.
- **A new live event type reaches a UI that may not render it** → #239 established this exact hazard: `@errand-ai/ui-components` below 0.18.0 renders unknown event types as empty elements via `FlatEntryView`'s final `v-else`. Any new event type needs the library to handle it, or it draws a blank row at the moment the operator most needs information. Check the library version and add the type before shipping the emission.
- **Making failure visible may reveal it is common** → Production shows one task failing compaction repeatedly. If the true rate is higher than the single observed case suggests, this change will surface it in the UI without a corresponding fix. That is the correct outcome, but expect it.

## Migration Plan

One Alembic migration (next number is 031; head is currently 030) adding the peak-context and ceiling columns to `tasks`, nullable — every existing row predates the measurement and must stay NULL rather than be backfilled with a fabricated value.

Rollback is the down migration plus removing the response fields. The event type and settings card carry no persistent state.

## Open Questions

- Should peak context appear on the task card, in the task detail view, or only via the API? The answer determines how much frontend work this is.
- Does a task that is retried record the peak of its last attempt or the maximum across attempts? Retries reset context, so the per-attempt peak is the meaningful figure, but the column is per task.
- Should the compaction-failure event also fire on the *recovery* transition, so an operator who saw the failure sees it resolve? The runner already logs recovery at `WARNING`.
