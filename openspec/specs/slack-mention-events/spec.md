## MODIFIED Requirements

### Requirement: Extracted event processing function
The Slack event processing logic SHALL be extracted from the `POST /slack/events` route handler into a standalone async function that can be called from both the HTTP route and the cloud webhook dispatcher.

#### Scenario: HTTP route calls extracted function
- **WHEN** a Slack event arrives at `POST /slack/events` and passes signature verification
- **THEN** the route handler SHALL call the extracted `process_slack_event(body: bytes)` function
- **THEN** behavior SHALL be identical to the existing implementation (url_verification handling, app_mention processing, duplicate detection)

#### Scenario: Cloud dispatcher calls extracted function
- **WHEN** a Slack events webhook is received via the cloud WebSocket relay
- **THEN** the cloud dispatcher SHALL call `process_slack_event(body: bytes)` directly
- **THEN** signature verification SHALL NOT be performed (already done by errand-cloud)
- **THEN** url_verification events SHALL be ignored (already handled by errand-cloud)

#### Scenario: Function signature
- **WHEN** `process_slack_event` is called
- **THEN** it SHALL accept `body: bytes` as its primary parameter
- **THEN** it SHALL return a JSON-serializable response dict (for HTTP route use) or None (for cloud dispatch where no HTTP response is needed)
