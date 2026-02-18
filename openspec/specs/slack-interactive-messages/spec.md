## ADDED Requirements

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
