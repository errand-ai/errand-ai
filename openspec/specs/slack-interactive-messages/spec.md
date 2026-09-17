## Purpose

Slack interactivity endpoint for handling button clicks and menu selections on task messages.

## Requirements

### Requirement: Slack interactions endpoint

The backend SHALL expose `POST /slack/interactions` that receives Slack interactivity payloads (button clicks, menu selections). The endpoint SHALL verify the Slack request signature using the existing `verify_slack_request` dependency. The payload is form-encoded with a `payload` field containing JSON.

#### Scenario: Button click dispatched
- **WHEN** Slack sends an interaction payload with `type: "block_actions"` and action `action_id: "task_status"`, `value: "<task_uuid>"`
- **THEN** the endpoint calls the existing `handle_status` handler with the task UUID and returns the Block Kit response

#### Scenario: View Output button clicked
- **WHEN** Slack sends an interaction payload with `type: "block_actions"` and action `action_id: "task_output"`, `value: "<task_uuid>"`
- **THEN** the endpoint calls the existing `handle_output` handler with the task UUID and returns the Block Kit response

#### Scenario: Invalid signature rejected
- **WHEN** an interaction request has an invalid Slack signature
- **THEN** the endpoint returns HTTP 403

#### Scenario: Unknown action ID
- **WHEN** an interaction payload contains an unrecognized `action_id`
- **THEN** the endpoint returns HTTP 200 with an empty body (Slack requires 200 for all interactions)

### Requirement: Interactive buttons in task confirmation

The `task_created_blocks()` Block Kit builder SHALL include an `actions` block with two buttons after the existing context block:

1. **View Status** button: `action_id: "task_status"`, `value: "<full-task-uuid>"`
2. **View Output** button: `action_id: "task_output"`, `value: "<full-task-uuid>"`

#### Scenario: Confirmation includes action buttons
- **WHEN** a task is created (from either slash command or mention)
- **THEN** the Block Kit response includes an actions block with "View Status" and "View Output" buttons

#### Scenario: Button value contains full UUID
- **WHEN** the View Status button is rendered for task `a1b2c3d4-e5f6-7890-abcd-ef1234567890`
- **THEN** the button's `value` field is `a1b2c3d4-e5f6-7890-abcd-ef1234567890` (full UUID, not prefix)

### Requirement: Extracted interaction processing function
The Slack interaction processing logic SHALL be extracted from the `POST /slack/interactions` route handler into a standalone async function that can be called from both the HTTP route and the cloud webhook dispatcher.

#### Scenario: HTTP route calls extracted function
- **WHEN** a Slack interaction arrives at `POST /slack/interactions` and passes signature verification
- **THEN** the route handler SHALL call the extracted `process_slack_interaction(body: bytes, session)` function
- **THEN** behavior SHALL be identical to the existing implementation

#### Scenario: Cloud dispatcher calls extracted function
- **WHEN** a Slack interactivity webhook is received via the cloud WebSocket relay
- **THEN** the cloud dispatcher SHALL call `process_slack_interaction(body: bytes, session)` directly
- **THEN** responses SHALL be sent via `response_url` (already the existing pattern for block_actions)

### Requirement: Draft actions dispatched from interactions

The interactions endpoint SHALL dispatch `block_actions` payloads whose `action_id` is `task_spec_submit`, `task_spec_run` or `task_spec_cancel`, with `value` set to the draft id, to the Slack intake adapter (see `task-spec-intake`). It SHALL resolve the clicking user's identity before acting, read `task_spec_submit` answers from the payload's `state.values`, and deliver the resulting message by replacing the original through the payload's `response_url`. It SHALL acknowledge with HTTP 200 immediately in all cases, carrying out the action afterwards, because a classifier call can outlast Slack's three-second acknowledgement window.

#### Scenario: Submit answers
- **WHEN** the draft's owner clicks Submit with answers filled in
- **THEN** the answers are passed to `clarify.answer` keyed by question id, and the original message is replaced with the next questions or the confirm card

#### Scenario: Run from a draft message
- **WHEN** the draft's owner clicks Run or Just run it
- **THEN** the draft is confirmed, and the original message is replaced with the task-created confirmation

#### Scenario: Expired or finished draft
- **WHEN** a draft action targets a draft that is expired, confirmed, or abandoned
- **THEN** the original message is replaced with a notice that the draft is no longer active, and no task is created
