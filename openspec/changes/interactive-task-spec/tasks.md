## 1. Branch, version, and config

- [ ] 1.1 Create branch `interactive-task-spec` from an up-to-date `main` and bump `VERSION` (minor — new persisted model + new API + new endpoint).
- [ ] 1.2 Add `clarification_max_rounds` Setting (int, default 2) to the config migration; verify `models.py` Setting row exists for it (grep `config.py` for the `DEFAULT_*_SETTING` pattern).

## 2. Data model (`errand/models.py` + Alembic)

- [ ] 2.1 Read an existing model + its Alembic migration (e.g. `TaskProfile` / the most recent migration file `versions/*_task_profiles_add_*`) to match field-naming and relationship conventions.
- [ ] 2.2 Add `TaskSpecDraft` to `models.py` with: `id` (UUID pk), `owner_id`, `input_text`, `conversation` (JSON), `spec` (JSON), `questions` (JSON, nullable), `status` enum (`drafting`/`ready`/`confirmed`/`abandoned`), `round` (int default 0), `expires_at`, `resolved_task_id` FK -> `tasks.id` nullable, timestamps. Verify by: a fresh `python -c "from models import TaskSpecDraft; print(TaskSpecDraft.__table__.columns)"` loads cleanly.
- [ ] 2.3 Write the Alembic migration: `task_spec_drafts` table, the four status strings as a CHECK constraint (or enum), `owner_id` indexed, nullable FK to `tasks`. Verify: `alembic upgrade head` from a clean DB applies with no error.
- [ ] 2.4 Confirm `_is_external_client` / owner-resolution path is reusable for scoping (grep `auth.sub` usage in `main.py` `require_editor`).

## 3. Service layer (`errand/clarify.py` — new file)

- [ ] 3.1 Write failing tests for `clarify.start`: unambiguous input → `status="ready"`, empty questions; ambiguous input → `status="drafting"`, non-empty `questions`; round=0 set; draft owned by `owner`. Run with the project's existing `pytest tests/test_clarify.py` (create it).
- [ ] 3.2 Implement `clarify.start(input_text, owner, session) -> dict`: creates the draft row, loads profiles for context, calls `generate_title` once with `want_questions=True`. Inspect `generate_title`'s return shape — it must carry a `questions` list. Persist the first turn + spec + questions. Return `{draft_id, status, questions, spec_preview}`.
- [ ] 3.3 Write/extend the classifier so it can emit `questions` and folds answers: extend `LLMResult` with `questions: list[dict] | None` and teach `generate_title` (or a thin wrapper) to accept `history` and `round` and to return unresolved questions instead of `success=False, Needs Info`. Verify by: the existing `tests/test_llm.py` still passes (no behaviour change for the non-clarification path).
- [ ] 3.4 Implement `clarify.answer(draft_id, responses, session)`: append a user turn, increment `round`, re-invoke the classifier with full conversation, persist result. Enforce the `clarification_max_rounds` cap: if reaching the cap with questions still unresolved, force `status="ready"` + `questions_unresolved=True` instead of asking a third time. Verify by: a draft at round == max returns `ready` (not `drafting`).
- [ ] 3.5 Implement `clarify.confirm(draft_id, session)`: take the resolved spec, build a `TaskCreate`, call the existing `create_task` logic (refactor `create_task` so its body is reusable, not the HTTP handler), link `resolved_task_id`, set `status="confirmed"`. Verify by: a confirmed draft's `resolved_task_id` points at a real `tasks` row.
- [ ] 3.6 Add a cleanup path: a function that `abandons` expired drafts (`expires_at < now`) and sets them abandoned; wire it to run at startup + a lightweight periodic sweep. Verify by: a draft with `expires_at` in the past reads as 404.

## 4. API (`errand/main.py`)

- [ ] 4.1 Add `GET /api/task-specs` (list the caller's drafts) and `POST /api/task-specs` (`input_text` -> `clarify.start`). Reuse `require_editor`. Verify: returns the starter's `questions` or `ready` payload; unauthenticated → 401.
- [ ] 4.2 Add `POST /api/task-specs/{id}/answer` and `POST /api/task-specs/{id}/confirm`. Scope all three to `owner_id` (404 not 403 on mismatch). Verify by: user B answering user A's draft → 404.
- [ ] 4.3 Verify the full loop end-to-end with the test client: `start` (drafting/questions) → `answer` (ready) → `confirm` (201 from `POST /api/tasks` equivalent). Run `pytest tests/test_task_spec_api.py` (create it).

## 5. Slack adapter (`errand/webhook_receiver.py` / `errand/integration_routes.py`)

- [ ] 5.1 Locate the existing Slack slash-command / `@`-mention entrypoint (grep `slash` / `@app` in `webhook_receiver.py`). Confirm it currently creates a task immediately.
- [ ] 5.2 Route inbound text through `clarify.start`. If questions come back, post a Slack message with block-kit buttons for `choice` questions and a text prompt for `free_text`; capture the slack thread ts on the draft (add `external_thread_ts` column — extension of step 2.2/2.3, amend migration if needed).
- [ ] 5.3 On a Slack reply matching an open draft's thread, call `clarify.answer`. On `ready`, post a confirm card (Run / Cancel). On Run, `clarify.confirm` → post the new task id.
- [ ] 5.4 Enforce: only the slack user matching `owner_id` may advance the draft. Verify by: a different Slack user replying in-thread → ignored, draft untouched.

## 6. Web frontend

- [ ] 6.1 Create `frontend/src/components/TaskSpecIntake.vue`: description box → conversation panel (model questions, user answers) → spec preview card → Run/Cancel. Call only `/api/task-specs` + `/confirm`. Use `@errand-ai/ui-components` card library for consistency with settings cards.
- [ ] 6.2 Wire it into the existing task-creation entry point on the kanban board (find where `POST /api/tasks` is currently called from the UI — grep `useApi.tasks` / `createTask`). Verify: the old path still works; the new intake is reachable from the same "new task" entry.
- [ ] 6.3 Frontend tests: `npx vitest run src/components/__tests__/TaskSpecIntake.test.ts` (create it) — mock the API, assert the ready-vs-questions branching and the confirm call.

## 7. Cross-repo wiring (if cloud is involved)

- [ ] 7.1 Confirm the inbound Slack path delivery: `errand-cloud` webhook relay → WebSocket → `webhook_receiver.py`. This path already exists for *inbound events*; confirm no change needed in `errand-cloud` for text that *originates* from Slack via the slash-command response (Slack calls the errand instance directly, not via the tunnel — verify by reading the slash-command registration in `integration_routes.py`).
- [ ] 7.2 Flag to the user: if Slack is expected to DM a self-hosted instance behind NAT, document whether a tunnel is required for the slash-command callback. (This is a deployment-config note, not a code change.)

## 8. Verification

- [ ] 8.1 `pytest tests/test_clarify.py tests/test_task_spec_api.py -q` — all pass.
- [ ] 8.2 `npx vitest run src/components/__tests__/TaskSpecIntake.test.ts` — pass.
- [ ] 8.3 `alembic upgrade head` against a fresh DB — clean.
- [ ] 8.4 `openspec validate --change interactive-task-spec` — clean.
- [ ] 8.5 End-to-end: start a draft from ambiguous input → answer twice → confirm → task appears on the kanban with the resolved spec.
