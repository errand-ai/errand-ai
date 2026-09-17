## Purpose

A `TaskSpecDraft` is a persisted, conversational specification of a task created *before* a real `Task` exists. It holds the user's original input, the clarifying question/answer conversation, the spec fields resolved so far, and a lifecycle status with a hard expiry. When the conversation resolves or is abandoned, the draft becomes either a confirmed spec (compiled into an ordinary task) or is deleted.

Unlike a `Task`, a draft is **ephemeral** and **owned**: it is user-scoped, expires after 24 hours of inactivity, and carries no scheduling or runner semantics — those exist only once it becomes a real task.

## ADDED Requirements

### Requirement: Draft entity persists conversation and partial spec

The system SHALL store a `task_spec_drafts` row per in-progress clarification, with fields:

- `id` (UUID, primary key)
- `owner_id` — the identity the draft belongs to, the same identity recorded in `tasks.created_by`: the token's `email` claim (falling back to `sub`) for web callers, or the resolved email (falling back to `slack:<user_id>`) for Slack callers; queries are scoped to it.
- `source` — `web` or `slack`.
- `input_text` — the original description the user submitted.
- `conversation` — ordered array of `{role: "user"|"assistant"|"system", content: str, ts: ISO8601}`; the clarifying exchange.
- `spec` — the task fields resolved so far: `{title?, description?, category?, execute_at?, repeat_interval?, repeat_until?, profile?}`. Absent fields are "not yet resolved".
- `questions` — the most recent set of open questions emitted by the model for the user (array of `{id, text, kind: "free_text"|"choice", choices?}`); null/empty when none are pending.
- `questions_unresolved` — boolean, true when the round cap forced the draft to `ready` while questions remained.
- `status` — enum: `drafting`, `ready`, `confirmed`, `abandoned`.
- `round` — integer, starts at 0, incremented each time the model is re-invoked with new answers.
- `expires_at` — datetime, set to 24h after the draft's last activity (creation or answer); the system SHALL refuse to operate on an expired draft and SHALL garbage-collect expired drafts.
- `external_channel_id`, `external_message_ts` — nullable; for Slack drafts, where the question message was posted.
- `created_at`, `updated_at` — standard timestamps.
- `resolved_task_id` — nullable foreign key to `tasks.id`; set when `confirmed`, to bind the two records for audit.

#### Scenario: Draft created on start

- **WHEN** `clarify.start(input_text, owner)` is called
- **THEN** a `task_spec_drafts` row exists with `round = 0`, `owner_id = owner`, `input_text = input_text`, and the fields the classifier resolved in `spec`
- **AND** `conversation` contains the user's input turn followed by exactly one assistant turn (the first clarifying questions or an immediate "ready" result)
- **AND** `status` is `drafting` when questions are pending and `ready` otherwise

#### Scenario: Answers fold into conversation

- **WHEN** `clarify.answer(draft_id, responses)` is called on an active drafting draft
- **THEN** a `user` turn is appended to `conversation` with the responses, `round` is incremented, and the model is re-invoked
- **AND** the resulting draft `spec` and `questions` are persisted, and `expires_at` is moved to 24h from now

#### Scenario: Drafts expire and are cleaned up

- **WHEN** a draft's `expires_at` has passed
- **THEN** a periodic sweep sets its `status` to `abandoned` and it is no longer operable; the sweep deletes `abandoned` drafts whose `expires_at` is more than 24h in the past

#### Scenario: Confirmed draft links to Task

- **WHEN** a `drafting`/`ready` draft is confirmed
- **THEN** a `tasks` row is created through the same Task-building code `POST /api/tasks` uses, from the resolved spec, and `task_spec_drafts.resolved_task_id` is set to that task's id, and the draft `status` becomes `confirmed`

### Requirement: Drafts are owner-scoped and access-controlled

The system SHALL enforce that no user can read, answer, confirm, or cancel a draft owned by another user.

#### Scenario: Cross-user draft access denied

- **WHEN** user A attempts `GET /api/task-specs/<id>` or `POST /answer` on a draft owned by user B
- **THEN** the request fails with 404 (not 403 — drafts are undisclosed)

### Requirement: Expired drafts are rejected at read and write

The system SHALL treat a draft whose `expires_at` is in the past as not found on any read or write operation.

#### Scenario: Expired drafts are rejected at read and write

- **WHEN** an operation targets a draft whose `expires_at` is in the past
- **THEN** it is treated as not found (404) and, on attempted answer, the client is told the session expired

### Requirement: Finished drafts cannot be advanced

The system SHALL reject `answer`, `confirm` and `cancel` on a draft whose status is `confirmed` or `abandoned` with HTTP 409, so a double-clicked Run cannot create two tasks.

#### Scenario: Confirming twice

- **WHEN** a draft that is already `confirmed` is confirmed again
- **THEN** the request fails with 409 and no second task is created
