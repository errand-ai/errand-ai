## Why

Today's task intake is a single shot: the user submits a one-line description and an LLM call (`generate_title` in `errand/llm.py`) classifies it into title/category/timing/profile in one pass. When anything outcome-changing is ambiguous, that call returns no clean description and the task lands tagged `"Needs Info"` — a dead-end card the user must find, edit by hand, and **re-run** manually. That is the weakest moment for a personal automation engine: the gap between "I said what I wanted" and "the agent understood what I wanted" is unbridgeable by a retry, because the original context is gone.

This matters because Errand's entry point is where it bleeds users. The engine is async, unattended, fire-and-forget by design — but entry is conversational and synchronous, and it's currently all-or-nothing. We already build tasks from more structured inputs (profiles, schedules, webhook triggers), and the agent can already emit `needs_input` + `questions` mid-run (the `"Input Needed"` tag flow in `errand/task_manager.py`). What's missing is a **bounded clarification loop at intake** so the single description becomes a small, resolved dialogue before the task ever exists.

This is a usability fix, not a model upgrade: two cheap local-model turns that prevent one wrong expensive agent run.

## What Changes

- Add a `TaskSpecDraft` persist model representing an in-progress, conversational intake: the original input, the question/answer conversation turns, the spec fields resolved so far, and a status (`drafting` → `ready` → `confirmed`/`abandoned`) with a 24h expiry.
- Add a `clarify.py` service layer: `start(intput, owner)` → emits the first clarifying question (or short-circuits to a final spec when the input is already unambiguous); `answer(draft_id, responses)` → folds the answers back in and either asks again or returns a `{status, spec_preview}` ready to confirm. Enforces a configurable round cap (`clarification_max_rounds`, default 2) and an explicit "just run with what we have" escape on every turn.
- Expose `GET/POST /api/task-specs` on the backend — a single API both the web frontend and the Slack inbound adapter call.
- The web frontend gains a small intake dialog: description box → conversation panel (questions + answers) → a spec **preview card** ("I'll do X, scheduled Y, under profile Z") with a confirm step. Confirmed drafts **compile back to the existing `TaskCreate` shape** (`POST /api/tasks`), so no engine change is needed to run the resulting task.
- The Slack slash-command / `@`-mention handler routes inbound text through the same draft flow instead of immediately creating a task: questions come back as block-kit buttons (plus free text), replies resolve in-thread, and confirm creates the task. Reuses the existing `errand-cloud` webhook → WebSocket tunnel delivery path.

## Capabilities

### New Capabilities

- `task-spec-draft-model`: the persisted draft entity with conversation history, spec fields, status lifecycle, and expiry.
- `task-spec-intake`: the clarification service — `start`/`answer`/resolve, round cap, escape hatch, spec preview.
- `task-spec-api`: the `GET/POST /api/task-specs` surface contract (request/response shapes, auth, owner-scoping).
- `task-spec-web-ui`: the intake/conversation flow in the frontend.
- `task-spec-slack-adapter`: routing inbound Slack text through the draft flow and back to Slack with block-kit questions; uses the existing cloud tunnel.

### Modified Capabilities

- `structured-task-events`: the task-creation event stream gains a `spec_draft_created` / `spec_draft_confirmed` pair of events so a confirmed spec's transition into a real task is observable (the events already exist for task lifecycle; this is a new pair at the draft boundary).
- `slack-inbound`: the existing slash-command/mention entrypoint gains a "clarify before create" mode (currently it creates immediately).

## Impact

- `errand/models.py`: new `TaskSpecDraft` table + Alembic migration.
- `errand/clarify.py`: **new file** — the service layer.
- `errand/main.py`: new routes `GET/POST /api/task-specs`; confirmed draft calls into the existing `create_task` path.
- `errand/task_manager.py`: minimal — `create_task` already accepts `TaskCreate`; the draft resolves to it. No change to the async runner.
- `errand/webhook_receiver.py` / `errand/integration_routes.py`: Slack inbound handler routes through `clarify.start`/`answer`.
- `frontend/src/`: new intake dialog component + wiring into the existing task-creation entry point.
- `openspec/config.yaml`: optional `clarification_max_rounds` setting.
- No change to the task runner container, the sandbox, scheduling, or repeat machinery — the resolved draft is a plain `TaskCreate`.
