## Purpose

A `TaskSpecDraft` is a persisted, conversational specification of a task created *before* a real `Task` exists. It holds the user's original input, the clarifying question/answer conversation, the spec fields resolved so far, and a lifecycle status with a hard expiry. When the conversation resolves or is abandoned, the draft becomes either a confirmed spec (compiled to a `TaskCreate`) or is deleted.

Unlike a `Task`, a draft is **ephemeral** and **owned**: it is user-scoped, expires after 24 hours of inactivity, and carries no scheduling or runner semantics — those exist only once it becomes a real task.

## ADDED Requirements

### Requirement: Draft entity persists conversation and partial spec

The system SHALL store a `task_spec_drafts` row per in-progress clarification, with fields:

- `id` (UUID, primary key)
- `owner_id` — the authenticated user identity (`auth.sub`) the draft belongs to; queries are scoped to it.
- `input_text` — the original description the user submitted.
- `conversation` — ordered array of `{role: "user"|"assistant"|"system", content: str, ts: ISO8601}`; the clarifying exchange.
- `spec` — partial `TaskCreate` shape resolved so far: `{title?, description?, category?, execute_at?, repeat_interval?, repeat_until?, profile?}`. Absent fields are "not yet resolved".
- `questions` — the most recent set of open questions emitted by the model for the user (array of `{id, text, kind: "free_text"|"choice", choices?}`); null/empty when none are pending.
- `status` — enum: `drafting`, `ready`, `confirmed`, `abandoned`.
- `round` — integer, starts at 0, incremented each time the model is re-invoked with new answers.
- `expires_at` — ISO8601 datetime, computed as `created_at + 24h`; the system SHALL refuse to operate on an expired draft and SHALL garbage-collect expired drafts.
- `created_at`, `updated_at` — standard timestamps.
- `resolved_task_id` — nullable foreign key to `tasks.id`; set when `confirmed`, to bind the two records for audit.

#### Scenario: Draft created on start

- **WHEN** `clarify.start(input_text, owner)` is called
- **THEN** a `task_spec_drafts` row exists with `status = "drafting"`, `round = 0`, `spec = {}` (all fields null), `input_text = input_text`, and a single system turn recording the start
- **AND** `conversation` contains exactly one assistant turn (the first clarifying question or an immediate "ready" result)

#### Scenario: Answers fold into conversation

- **WHEN** `clarify.answer(draft_id, responses)` is called on an active drafting draft
- **THEN** a `user` turn is appended to `conversation` with the responses, `round` is incremented, and the model is re-invoked
- **AND** the resulting draft `spec` and `questions` are persisted

#### Scenario: Drafts expire and are cleaned up

- **WHEN** 24 hours have elapsed since a draft's `updated_at`
- **THEN** the draft's `status` becomes `abandoned` and it is no longer operable; a nightly garbage-collection job deletes `abandoned` drafts

#### Scenario: Confirmed draft links to Task

- **WHEN** a `drafting`/`ready` draft is confirmed
- **THEN** a `tasks` row is created via the existing `create_task` path using the resolved spec, and `task_spec_drafts.resolved_task_id` is set to that task's id, and the draft `status` becomes `confirmed`

### Requirement: Drafts are owner-scoped and access-controlled

The system SHALL enforce that no user can read, answer, or confirm a draft owned by another user.

#### Scenario: Cross-user draft access denied

- **WHEN** user A attempts `GET /api/task-specs/<id>` or `POST /answer` on a draft owned by user B
- **THEN** the request fails with 404 (not 403 — drafts are undisclosed)

### Requirement: Expired drafts are rejected at read and write

The system SHALL treat a draft whose `expires_at` is in the past as not found on any read or write operation.

#### Scenario: Expired drafts are rejected at read and write

- **WHEN** an operation targets a draft whose `expires_at` is in the past
- **THEN** it is treated as not found (404) and, on attempted answer, the client is told the session expired
