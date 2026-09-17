## 1. Branch, version, and config

- [x] 1.1 Create branch `interactive-task-spec` from an up-to-date `main` and bump `VERSION` (minor — new persisted model + new API + new endpoint).
- [x] 1.2 Add `clarification_max_rounds` (int, default 2) to `SETTINGS_REGISTRY` in `errand/settings_registry.py` and a validator in `_SETTING_VALIDATORS` (`main.py`). Verify: `resolve_setting_value(session, "clarification_max_rounds")` returns `(2, "default")` on an empty DB.

## 2. Data model (`errand/models.py` + Alembic)

- [x] 2.1 Read an existing model + its Alembic migration (e.g. `TaskProfile`, `030_add_eval_framework.py`) to match field-naming and relationship conventions.
- [x] 2.2 Add `TaskSpecDraft` to `models.py` with: `id` (UUID pk), `owner_id`, `source`, `input_text`, `conversation` (JSON), `spec` (JSON), `questions` (JSON, nullable), `questions_unresolved` (bool), `status` (`drafting`/`ready`/`confirmed`/`abandoned`), `round` (int default 0), `expires_at`, `external_channel_id` / `external_message_ts` (nullable), `resolved_task_id` FK -> `tasks.id` nullable, timestamps. Verify: `from models import TaskSpecDraft` loads cleanly.
- [x] 2.3 Write migration `033`: `task_spec_drafts` table, the four status strings as a CHECK constraint, `owner_id` indexed, nullable FK to `tasks` (`ON DELETE SET NULL`). Verify: `alembic upgrade head` from a clean DB applies with no error.
- [x] 2.4 Add an owner-identity helper for web callers matching `created_by` (`email` claim, falling back to `sub`); Slack callers use `resolve_slack_email` with the `slack:<user_id>` fallback.

## 3. Service layer (`errand/clarify.py` — new file)

- [x] 3.1 Write failing tests for `clarify.start`: unambiguous input → `status="ready"`, empty questions; ambiguous input → `status="drafting"`, non-empty `questions`; round=0 set; draft owned by `owner`; no model → `ready` with the raw input. Create `errand/tests/test_clarify.py`.
- [x] 3.2 Extend the classifier: `LLMResult.questions`, and `generate_title(..., want_questions=False, history=None)` — the prompt gains a `questions` field and the conversation only when asked. Verify: `errand/tests/test_llm.py` still passes, and a test asserts the default prompt is unchanged.
- [x] 3.3 Implement `clarify.start(session, input_text, owner, source)`: creates the draft row, loads profiles for context, calls `generate_title` once with `want_questions=True`, persists the turns + spec + questions, returns the draft view.
- [x] 3.4 Implement `clarify.answer(session, draft_id, owner, responses)`: append a user turn, increment `round`, re-invoke the classifier with the full conversation, persist the result, extend `expires_at`. Enforce the `clarification_max_rounds` cap: an answer that brings `round` to the cap with questions still pending forces `status="ready"` + `questions_unresolved=True`. Verify: with max=2 the second answer returns `ready`, not `drafting`.
- [x] 3.5 Extract the Task-building half of `create_task` (`main.py`) into `create_task_from_fields` in a new `errand/task_creation.py` (with `TaskResponse` and `sync_tags`, so `clarify` can share it without importing `main`) (status routing, position, tags, `is_eval`, `task_created` event), and have `create_task` call it. Verify: the existing `create_task` tests pass unchanged.
- [x] 3.6 Implement `clarify.confirm(session, draft_id, owner, extra_tags=())` via `create_task_from_fields` (profile name → id), link `resolved_task_id`, set `status="confirmed"`; and `clarify.cancel`. Finished drafts raise a conflict (409). Verify: a confirmed draft's `resolved_task_id` points at a real `tasks` row; confirming twice creates one task.
- [x] 3.7 Add `sweep_expired_drafts`: marks expired drafts `abandoned` and deletes abandoned drafts expired more than 24h ago; run it at startup and periodically from the lifespan. Verify: a draft with `expires_at` in the past reads as not found.

## 4. API (`errand/main.py`)

- [x] 4.1 Add `GET /api/task-specs`, `GET /api/task-specs/{id}` and `POST /api/task-specs` (`input` -> `clarify.start`). Reuse `require_editor`. Verify: returns the `questions` or `ready` payload; unauthenticated → 401.
- [x] 4.2 Add `POST /api/task-specs/{id}/answer`, `/confirm` and `/cancel`. Scope all to the owner (404 not 403 on mismatch; 409 on finished drafts). Verify: user B answering user A's draft → 404.
- [x] 4.3 Verify the full loop with the test client: `start` (drafting/questions) → `answer` (ready) → `confirm` (201, task listed by `GET /api/tasks`). Create `errand/tests/test_task_spec_api.py`.

## 5. Slack adapter (`errand/platforms/slack/`)

- [x] 5.1 Confirm `/task new` (`handlers.handle_new`) and `app_mention` (`routes._handle_mention`) currently create a task immediately.
- [x] 5.2 Add draft Block Kit builders to `blocks.py`: questions message (plain-text inputs / static selects + Submit, Just run it, Cancel), confirm card (preview + Run / Cancel, unresolved questions as read-only context), and inactive/cancelled notices.
- [x] 5.3 Route `/task new` and `app_mention` through `clarify.start`; the mention posts the draft message in-thread and records `external_channel_id` / `external_message_ts` on the draft.
- [x] 5.4 Dispatch `task_spec_submit` / `task_spec_run` / `task_spec_cancel` in `process_slack_interaction`: answers from `state.values` → `clarify.answer`; Run → `clarify.confirm` (tag `slack`) → task confirmation + `SlackMessageRef`; Cancel → `clarify.cancel`. Replace the original message via `response_url`.
- [x] 5.5 Enforce: only the Slack user whose resolved identity matches `owner_id` may advance the draft. Verify: a different Slack user clicking Submit → ephemeral notice, draft untouched.
- [x] 5.6 Update the existing Slack tests (`test_slack_*`) for the draft-first behaviour and add tests for the new actions.

## 6. Web frontend

- [x] 6.1 Create `frontend/src/components/TaskSpecIntake.vue`: description box → conversation panel (model questions, user answers) → spec preview card → Run / Just run it / Cancel. Call only the `/api/task-specs` endpoints. Match the styling of the existing task form.
- [x] 6.2 Wire it into the existing task-creation entry point on the kanban board (where `POST /api/tasks` is currently called from the UI). Verify: the new intake is reachable from the same "new task" entry and the board updates on confirm.
- [x] 6.3 Frontend tests: `src/components/__tests__/TaskSpecIntake.test.ts` — mock the API, assert the ready-vs-questions branching, the round-cap read-only state, and the confirm call.

## 7. Delivery path (cloud relay)

- [x] 7.1 Confirm the cloud relay (`cloud_dispatch.py`) already forwards Slack commands, events and interactions to the same `process_slack_*` functions, so the draft actions need no `errand-cloud` change.
- [x] 7.2 Record for the user whether a self-hosted instance behind NAT needs the tunnel for interactions (deployment note, not a code change).

## 8. Verification

- [x] 8.1 Full errand pytest suite passes (`DATABASE_URL="sqlite+aiosqlite:///:memory:" errand/.venv/bin/python -m pytest errand/tests/ -q`).
- [x] 8.2 Full frontend vitest suite passes.
- [x] 8.3 `alembic upgrade head` against a fresh Postgres DB — clean.
- [x] 8.4 `openspec validate interactive-task-spec` — clean.
- [x] 8.5 End-to-end on the local stack: start a draft from ambiguous input → answer → confirm → task appears on the kanban with the resolved spec.
