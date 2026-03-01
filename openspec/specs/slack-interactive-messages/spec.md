## MODIFIED Requirements

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
