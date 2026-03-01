## ADDED Requirements

### Requirement: Webhook payload routing by integration and endpoint type
The cloud webhook dispatcher SHALL route incoming webhook payloads to the appropriate handler based on the `integration` and `endpoint_type` fields from the WebSocket message.

#### Scenario: Slack events webhook
- **WHEN** a cloud-relayed message has `integration: "slack"` and `endpoint_type: "events"`
- **THEN** the dispatcher SHALL call the Slack event processing function with the raw body bytes
- **THEN** signature verification SHALL be skipped (errand-cloud already verified)

#### Scenario: Slack commands webhook
- **WHEN** a cloud-relayed message has `integration: "slack"` and `endpoint_type: "commands"`
- **THEN** the dispatcher SHALL call the Slack command processing function with the raw body bytes

#### Scenario: Slack interactivity webhook
- **WHEN** a cloud-relayed message has `integration: "slack"` and `endpoint_type: "interactivity"`
- **THEN** the dispatcher SHALL call the Slack interaction processing function with the raw body bytes

#### Scenario: Unknown integration
- **WHEN** a cloud-relayed message has an unrecognized `integration` value
- **THEN** the dispatcher SHALL log a warning and skip processing
- **THEN** the message SHALL still be ACKed (to prevent redelivery of unprocessable messages)

### Requirement: Slack command responses via response_url
When processing Slack commands received via cloud relay, all responses SHALL be sent via the Slack `response_url` rather than as direct HTTP responses.

#### Scenario: Slash command response
- **WHEN** a Slack slash command is processed via cloud relay
- **THEN** the handler SHALL extract the `response_url` from the command payload
- **THEN** the handler SHALL POST the Block Kit response to the `response_url`
- **THEN** the original webhook acknowledgment (200 OK) was already sent by errand-cloud

#### Scenario: Missing response_url
- **WHEN** a Slack slash command payload does not contain a `response_url`
- **THEN** the handler SHALL log a warning and discard the response (no way to deliver it)
