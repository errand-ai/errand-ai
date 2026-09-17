## Context

Entry today is a one-shot LLM classification (`errand/llm.py::generate_title`): the user submits a description, the classifier parses title/category/timing/profile, and on any ambiguity the task is tagged `"Needs Info"` and parked — requiring the user to find the card, hand-edit the description, and re-trigger. The agent already supports mid-run question/answer via `needs_input` + `questions` (see `errand/task_manager.py`), and Slack is already an intake channel (`/task new`, `@`-mentions in `errand/platforms/slack/routes.py`) and a status channel. The gap is a **pre-execution** loop, on both the web UI and incoming Slack text.

## Goals / Non-Goals

**In scope:**
- A persisted `TaskSpecDraft` (drafting → ready → confirmed/abandoned, 24h inactivity expiry) that is owner-scoped and access-controlled.
- A `clarify.py` service (`start` / `answer` / `confirm` / `cancel`) enforcing a round cap and an explicit "just run" escape on every turn.
- The classifier prompt is the *existing* `generate_title` prompt, extended to optionally emit a `questions` array — NOT a new model integration.
- A single `/api/task-specs` contract consumed by the web frontend; the Slack adapter calls the same service layer in-process.
- Confirmed drafts become ordinary tasks through the same Task-building code `POST /api/tasks` uses, linking back via `resolved_task_id`.

**Non-goals:**
- No streaming runtime chat — Errand stays async once the task exists.
- No changes to the task runner sandbox, scheduling, repeat machinery, or the agent's execution model.
- Not a general "chat with your task" surface post-run.
- No new Slack event subscriptions or OAuth scopes.
- No new draft-boundary events on the task event stream; a confirmed draft emits the existing `task_created`.

## Decisions

### Decision 1: Draft as a persisted object, not an ephemeral chat

A `drafting` draft persists across page closes, device switches, and Slack handoffs; an ephemeral in-memory chat cannot survive the user walking away and is unrecoverable for Slack. A persisted draft is owned and expires, which makes the security posture (owner-scoped queries, 404-not-403 on cross-user access) explicit and testable.

*Alternative considered: in-memory conversation keyed by session id.* Rejected: breaks the multi-surface story (web → phone → Slack) and any "you have a pending clarification" UX.

### Decision 2: Reuse `generate_title`'s prompt with a `questions` output field

`errand/llm.py::generate_title` already classifies and strips scheduling noise into a `LLMResult`. Extending that prompt to optionally return `"questions": [...]` when outcome-changing facts are missing reuses a tested path and uses the same configured provider (so local models work for free). The extension is opt-in (`want_questions=True`, optional `history`), so the prompt sent by existing callers is byte-for-byte unchanged.

A classifier that was never reached (no model, request failed) resolves the draft to `ready` with the raw input as description — the same reasoning the web intake already applies: nothing was asked, so nothing is missing from what the user wrote. An unusable response also resolves to `ready` with the raw input; the user sees the preview and decides.

*Alternative considered: a separate "clarifier" model/prompt.* Rejected as duplicative and as a risk to consistency between draft and run-time parsing.

### Decision 3: Confirm shares `POST /api/tasks`'s Task-building code

`TaskCreate` is `{input: str}` — `POST /api/tasks` classifies that input itself. Posting a confirmed draft's text back through it would re-run classification and discard the spec the user just agreed to. Instead, the half of `create_task` that turns resolved fields into a `Task` (status routing, column position, tags, `is_eval`, the `task_created` event) moves into a helper, `create_task_from_fields`, which both `create_task` and `clarify.confirm` call. The HTTP contract of `POST /api/tasks` is unchanged, and so is the async runner.

*Alternative considered: widening `TaskCreate` with optional resolved fields.* Rejected: it changes a public API contract for an internal need.

### Decision 4: Round cap + mandatory escape, hard-wired

`clarification_max_rounds` (default 2) counts answer rounds. `start` may ask; each `answer` increments `round`; when an answer brings `round` to the cap and the model still has questions, the draft is forced to `ready` with `questions_unresolved = true`, and the client shows those questions as read-only context with a Run/Cancel card — never another question. With the default, a user is asked at most twice. Every turn the user sees an explicit "run with what we have" action (`confirm` is accepted on a `drafting` draft). This prevents the "endless clarification" failure mode.

### Decision 5: Owner = the email identity tasks already record

A draft's `owner_id` is the identity `create_task` writes to `tasks.created_by`: the token's `email` claim, falling back to `sub` when a token carries no email. Slack resolves its user to an email via `resolve_slack_email` (falling back to `slack:<user_id>`, exactly as `created_by` does today). Using `auth.sub` instead would make a Slack-started draft invisible on the web, since a Slack user id can only be mapped to an email. No new identity system.

### Decision 6: Slack answers arrive as interactive input blocks

The Slack app subscribes only to `app_mention` events, so a plain thread reply never reaches errand; receiving one would need `message.*` subscriptions, history scopes, and a re-install. Instead the question message carries Block Kit `input` blocks (plain-text inputs for `free_text` questions, static selects for `choice` questions) plus **Submit**, **Just run it** and **Cancel** buttons whose `value` is the draft id. A button click is a `block_actions` payload on the existing `POST /slack/interactions` endpoint, carrying the inputs' `state.values`, and is already forwarded by the cloud relay. Updates replace the original message via the payload's `response_url`, which works for both the ephemeral slash-command reply and the in-thread mention reply.

Only a clicking user whose resolved identity equals the draft's `owner_id` may advance it; anyone else is told so ephemerally and the draft is untouched.

## Risks / Trade-offs

- [Risk] Ambiguity detection is heuristic — the model may emit "I'm not sure" questions on unambiguous input. → **Mitigation:** round cap + "just run" escape make over-asking cheap rather than blocking.
- [Risk] A confused agent could emit outcome-irrelevant questions. → **Mitigation:** the extended prompt instructs *only* ask about outcome-changing unknowns, and caps the count at 3.
- [Risk] Slack payloads are attacker-influenced. → **Mitigation:** button values are draft ids checked against the clicking user's identity; free-text answers are treated as untrusted input and re-classified, never executed; the classifier prompt's "do not perform the task" rule is inherited.
- [Trade-off] Every Slack/web task now takes a confirm click, even when the input was unambiguous. This is the point of the preview card; the "Needs Info" dead end it replaces cost more.
- [Trade-off] `"Needs Info"` still exists for the `POST /api/tasks` path (kept for API/MCP clients) and the external-client case. The intake loop only governs interactive creation.

## Migration Plan

- **Backward compatible.** No existing task field changes. The `task_spec_drafts` table is additive; `POST /api/tasks` keeps its contract.
- `clarification_max_rounds` is a registry setting defaulting to 2; no data migration.
- Drafts are ephemeral: expired drafts are marked `abandoned` by a periodic sweep and deleted a further 24h later.

## Open Questions

- Whether the Slack adapter needs a hard cap distinct from the global `clarification_max_rounds`. Resolved: keep one.
