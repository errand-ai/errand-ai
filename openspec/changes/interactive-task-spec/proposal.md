## Why

Today's task intake is a single shot: the user submits a one-line description and an LLM call (`generate_title` in `errand/llm.py`) classifies it into title/category/timing/profile in one pass. When anything outcome-changing is ambiguous, that call returns no clean description and the task lands tagged `"Needs Info"` — a dead-end card the user must find, edit by hand, and **re-run** manually. That is the weakest moment for a personal automation engine: the gap between "I said what I wanted" and "the agent understood what I wanted" is unbridgeable by a retry, because the original context is gone.

This matters because Errand's entry point is where it bleeds users. The engine is async, unattended, fire-and-forget by design — but entry is conversational and synchronous, and it's currently all-or-nothing. We already build tasks from more structured inputs (profiles, schedules, webhook triggers), and the agent can already emit `needs_input` + `questions` mid-run (the `"Input Needed"` tag flow in `errand/task_manager.py`). What's missing is a **bounded clarification loop at intake** so the single description becomes a small, resolved dialogue before the task ever exists.

This is a usability fix, not a model upgrade: two cheap local-model turns that prevent one wrong expensive agent run.

## What Changes

- Add a `TaskSpecDraft` persisted model representing an in-progress, conversational intake: the original input, the question/answer conversation turns, the spec fields resolved so far, and a status (`drafting` → `ready` → `confirmed`/`abandoned`) with a 24h inactivity expiry. Drafts are owned by the same identity recorded in `tasks.created_by` (the user's email), so a draft started in Slack is the same person's draft on the web.
- Add a `clarify.py` service layer: `start(input, owner)` → emits the first clarifying questions (or short-circuits to a final spec when the input is already unambiguous); `answer(draft_id, responses)` → folds the answers back in and either asks again or returns a `{status, spec_preview}` ready to confirm; `confirm` and `cancel`. Enforces a configurable round cap (`clarification_max_rounds` setting, default 2) and an explicit "just run with what we have" escape on every turn.
- Expose `/api/task-specs` on the backend (list, get, start, answer, confirm, cancel) — a single API the web frontend calls; the Slack adapter calls the same service layer.
- The web frontend gains a small intake dialog: description box → conversation panel (questions + answers) → a spec **preview card** ("I'll do X, scheduled Y, under profile Z") with a confirm step.
- Confirmed drafts create an ordinary task through a **shared task-creation helper** extracted from `POST /api/tasks` (`TaskCreate` carries only raw `input`, so re-posting it would re-classify and discard the resolved spec). The async engine is unchanged.
- The Slack `/task new` command and `@`-mention handler route inbound text through the same draft flow instead of immediately creating a task: questions come back as a Block Kit message with input blocks (text inputs for free-text questions, selects for choice questions) and Submit / Just run it / Cancel buttons. Answers arrive through the existing `POST /slack/interactions` endpoint (and the cloud relay that already forwards it) — no new event subscriptions or OAuth scopes.

## Capabilities

### New Capabilities

- `task-spec-draft-model`: the persisted draft entity with conversation history, spec fields, status lifecycle, owner scoping and expiry.
- `task-spec-intake`: the clarification service (`start`/`answer`/`confirm`/`cancel`, round cap, escape hatch, spec preview) and the surfaces that use it — the `/api/task-specs` API, the web intake dialog, and the Slack adapter.

### Modified Capabilities

- `slack-commands`: `/task new` starts a clarification draft instead of creating a task immediately.
- `slack-mention-events`: an `app_mention` starts a clarification draft in-thread instead of creating a task immediately.
- `slack-interactive-messages`: the interactions endpoint dispatches the draft actions (submit answers, just run, cancel).

## Impact

- `errand/models.py`: new `TaskSpecDraft` table + Alembic migration.
- `errand/clarify.py`: **new file** — the service layer.
- `errand/llm.py`: `generate_title` gains optional `want_questions` / `history` parameters; `LLMResult` gains `questions`. The existing prompt is unchanged when they are not used.
- `errand/main.py`: new `/api/task-specs` routes; the Task-building half of `create_task` moves into a reusable helper.
- `errand/settings_registry.py`: new `clarification_max_rounds` setting.
- `errand/platforms/slack/routes.py`, `handlers.py`, `blocks.py`: Slack intake routes through `clarify`.
- `frontend/src/`: new intake dialog component + wiring into the existing task-creation entry point.
- No change to the task runner container, the sandbox, scheduling, or repeat machinery.
