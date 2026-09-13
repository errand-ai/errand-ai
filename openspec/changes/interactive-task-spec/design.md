## Context

Entry today is a one-shot LLM classification (`errand/llm.py::generate_title`): the user submits a description, the classifier parses title/category/timing/profile, and on any ambiguity the task is tagged `"Needs Info"` and parked — requiring the user to find the card, hand-edit the description, and re-trigger. The agent already supports mid-run question/answer via `needs_input` + `questions` (see `errand/task_manager.py` lines ~1460–1510), and Slack is already a *delivery* channel (tasks notify Slack outbound via the `errand-cloud` webhook relay). The gap is a **pre-execution** loop, on both the web UI and incoming Slack text.

## Goals / Non-Goals

**In scope:**
- A persisted `TaskSpecDraft` (drafting → ready → confirmed/abandoned, 24h expiry) that is owner-scoped and access-controlled.
- A `clarify.py` service (`start` / `answer` / `confirm`) enforcing a round cap and an explicit "just run" escape on every turn.
- The classifier prompt is the *existing* `generate_title` prompt, extended to optionally emit a `questions` array — NOT a new model integration.
- A single `GET/POST /api/task-specs` contract consumed by both the web frontend and the Slack inbound adapter.
- Confirmed drafts compile to the existing `POST /api/tasks` (no engine change), linking back via `resolved_task_id`.

**Non-goals:**
- No streaming runtime chat — Errand stays async once the task exists.
- No new task-creation backend — `confirm` delegates to the present `create_task`.
- No changes to the task runner sandbox, scheduling, repeat machinery, or the agent's execution model.
- Not a general "chat with your task" surface post-run.

## Decisions

### Decision 1: Draft as a persisted object, not an ephemeral chat

A `drafting` draft persists across page closes, device switches, and Slack thread handoffs; an ephemeral in-memory chat cannot survive the user walking away and is unrecoverable for Slack. A persisted draft is owned (tied to the tenant's `auth.sub`) and expires, which makes the security posture (owner-scoped queries, 404-not-403 on cross-user access) explicit and testable.

*Alternative considered: in-memory conversation keyed by session id.* Rejected: breaks the multi-surface story (web → phone → Slack) and any "you have a pending clarification" UX.

### Decision 2: Reuse `generate_title`'s prompt with a `questions` output field

`errand/llm.py::generate_title` already classifies and strips scheduling noise into a `LLMResult`. Extending that prompt to optionally return `"questions": [...]` when outcome-changing facts are missing reuses a tested path, uses the same configured provider (so local models work for free), and guarantees the resolved spec is in the exact shape `create_task` consumes. The escape hatch ("just run with what we have") is the existing `success=False, tag="Needs Info"` branch, re-framed as a best-effort compile.

*Alternative considered: a separate "clarifier" model/prompt.* Rejected as duplicative and as a risk to consistency between draft and run-time parsing.

### Decision 3: Confirm compiles to the existing `POST /api/tasks`

`create_task` already accepts a `TaskCreate` body (title/description/category/timing/repeat/profile). A confirmed draft is precisely that resolved object. `confirm(draft_id)` builds the `TaskCreate` and calls the same path, then sets `task_spec_drafts.resolved_task_id`. This keeps the async runner completely unchanged.

### Decision 4: Round cap + mandatory escape, hard-wired

`clarification_max_rounds` defaults to 2. When reached, the loop returns the best-effort spec tagged `questions_unresolved = true` and the client shows the final questions as read-only context with a Run/Cancel card — never a third question. Every turn the user sees an explicit "run with what we have" action regardless of the current question count. This prevents the "endless clarification" failure mode that makes chat-bots feel stuck.

### Decision 5: Slack thread = channel of record; owner = identity

Slack user id is mapped server-side to the tenant's user identity; only the matching owner may advance the draft, and the thread is the channel. No new identity system — reuse the existing `require_editor` / tenant resolution.

## Risks / Trade-offs

- [Risk] Ambiguity detection is heuristic — the model may emit "I'm not sure" questions on unambiguous input. → **Mitigation:** round cap + "just run" escape make over-asking cheap rather than blocking.
- [Risk] A confused agent could emit outcome-irrelevant questions (ask about tone when scope is what's unclear). → **Mitigation:** the extended prompt instructs *only* ask about outcome-changing unknowns; the `category`/`execute_at`/`repeat_interval` extraction is non-optional (falls back to `immediate` if truly absent).
- [Risk] Slack block-kit questions add surface for prompt injection via crafted button payloads. → **Mitigation:** button payloads are opaque ids into the draft, not free text; free-text answers are treated as untrusted input and re-classified, never executed; the classifier prompt's "do not perform the task" rule is inherited.
- [Trade-off] The `"Needs Info"` tag still exists for the *external client* case (`_is_external_client` in `task_manager.py` completes without review). That branch is untouched — the intake loop only governs interactive creation.

## Migration Plan

- **Backward compatible.** No existing task field changes. The `task_spec_drafts` table is additive.
- Existing `"Needs Info"` tasks and external-client behavior are unchanged.
- `clarification_max_rounds` defaults to 2 if the config key is absent (no migration needed).
- No data migration: drafts are ephemeral and self-delete after 24h.

## Open Questions

- Whether the Slack adapter needs a "this is your only chance" hard cap distinct from the global `clarification_max_rounds` (proposed: no — one setting, one rule). Resolved: keep one.
