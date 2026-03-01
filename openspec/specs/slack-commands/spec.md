## MODIFIED Requirements

### Requirement: Extracted command processing function
The Slack command processing logic SHALL be extracted from the `POST /slack/commands` route handler into a standalone async function that can be called from both the HTTP route and the cloud webhook dispatcher.

#### Scenario: HTTP route calls extracted function
- **WHEN** a Slack slash command arrives at `POST /slack/commands` and passes signature verification
- **THEN** the route handler SHALL call the extracted `process_slack_command(body: bytes, session)` function
- **THEN** behavior SHALL be identical to the existing implementation

#### Scenario: Cloud dispatcher calls extracted function
- **WHEN** a Slack commands webhook is received via the cloud WebSocket relay
- **THEN** the cloud dispatcher SHALL call `process_slack_command(body: bytes, session)` directly
- **THEN** the function SHALL send responses via `response_url` (extracted from the command payload) rather than returning a JSON response

#### Scenario: Response delivery via response_url for cloud relay
- **WHEN** a Slack command is processed via cloud relay
- **THEN** the handler SHALL POST the Block Kit response to the command's `response_url` via the Slack client
- **THEN** the channel message posting for new tasks (via `background_tasks`) SHALL still work normally (it uses the bot token, not the HTTP response)
