## 1. Branch and version

- [ ] 1.1 Branch from `main` as `context-usage-observability`
- [ ] 1.2 Bump `VERSION` (minor — additive schema and API, new event type, new settings surface)
- [ ] 1.3 Confirm whether `context-accounting-correctness` has landed. It changes when compaction fires, so peaks recorded either side of it describe different systems; record which is live when the baseline is taken

## 2. Settings card

Smallest of the three, no schema, no new events. Landing it first gives a way to exercise the ceiling while building the rest.

- [ ] 2.1 Add `max_context_tokens` to the compaction settings card in the frontend. The registry entry already exists in `errand/settings_registry.py` — this is UI only
- [ ] 2.2 Present it as the first field on the card, ahead of the three settings that respond to it
- [ ] 2.3 Tests: the field renders, writes through `PUT /api/settings`, and the default of 150000 shows when nothing is stored
- [ ] 2.4 Confirm an env-set `MAX_CONTEXT_TOKENS` displays as environment-sourced and is not silently overwritten by a UI save

## 3. Compaction failure as a live event

- [ ] 3.1 Check the `@errand-ai/ui-components` version in `frontend/package.json` and confirm it handles an unknown event type without rendering an empty row. #239 established that below 0.18.0 unknown types fall through `FlatEntryView`'s final `v-else` and draw a blank element — resolve this before emitting, not after
- [ ] 3.2 Define the event type and payload in the runner: reason and consecutive-failure count, nothing more. It must stay small enough to belong in the bounded replay buffer
- [ ] 3.3 Emit it from `_record_compaction_failure`, alongside the existing `context_snapshot` rather than instead of it
- [ ] 3.4 Confirm `LIVE_EXCLUDED_EVENT_TYPES` still contains `context_snapshot` and that the filter remains a set-membership test on type. It must not learn to branch on `data`
- [ ] 3.5 Tests: the failure event is published and buffered; the snapshot is neither; three consecutive failures produce three events with increasing counts
- [ ] 3.6 Decide whether recovery also emits an event. The runner already logs it at `WARNING`; an operator who saw the failure has no signal that it resolved

## 4. Persist peak context

- [ ] 4.1 Alembic migration `031` (head is `030`) adding nullable peak and ceiling columns to `tasks`. Nullable is load-bearing: existing rows predate the measurement and must not be backfilled with a fabricated value
- [ ] 4.2 Add the columns to the `Task` model using `Mapped[]` annotations, matching the SQLAlchemy 2.0 style used throughout
- [ ] 4.3 Track the running maximum `input_tokens` in `task_manager.py` where `llm_turn_end` is already parsed for the live path. Treat an all-zero usage block as no measurement, per #239
- [ ] 4.4 Write both columns on task completion. Record the `max_context_tokens` in force for that task, not the current setting at write time, in case it changed mid-run
- [ ] 4.5 Add both fields to `TaskResponse` and to `_task_to_dict` for event payloads
- [ ] 4.6 Tests: peak recorded on completion; NULL when no usage was reported; not recorded as zero; migration leaves existing rows NULL; fields present in the API response
- [ ] 4.7 Resolve what a retried task records. Retries reset context, so the per-attempt peak is the meaningful number, but the column is per task — decide and document rather than letting the last write win by accident

## 5. Surface it

- [ ] 5.1 Decide where peak context appears: task card, task detail, or API only. This determines the size of the frontend work and is the main open question from the design
- [ ] 5.2 Show it as a ratio against the stored ceiling rather than a bare token count. The bare number is uninterpretable once the ceiling moves
- [ ] 5.3 Handle the NULL case explicitly — absent measurement is not zero usage, and must not render as 0%

## 6. Verify

- [ ] 6.1 Backend and frontend suites green
- [ ] 6.2 `openspec validate --specs` passes, as the CI guard requires
- [ ] 6.3 Run a task that fails compaction and confirm the failure appears in the live view while the snapshot does not
- [ ] 6.4 Confirm the snapshot for that same task is still retrievable from Loki, so the new event has added a path rather than moved one
- [ ] 6.5 Compare a recorded peak against the Loki figure for the same task; they should agree
- [ ] 6.6 Expect this change to reveal how common compaction failure actually is. One production task failed three times; if the true rate is higher, it will now be visible without a corresponding fix — record the rate rather than acting on it here
