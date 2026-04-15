## MODIFIED Requirements

### Requirement: Webhook receiver HTTP endpoint

The system SHALL expose a `POST /webhooks/{source}` endpoint (e.g. `/webhooks/jira`, `/webhooks/github`) that receives incoming webhook payloads from external services. The endpoint SHALL NOT require authentication — it relies on HMAC signature verification instead. The endpoint SHALL return 200 immediately after validation and process the webhook asynchronously via a background task.

#### Scenario: Valid webhook received and accepted

- **WHEN** a POST request is made to `/webhooks/jira` with a valid HMAC signature and JSON body
- **THEN** the response status is 200, the body contains `{"status": "accepted"}`, and the payload is queued for asynchronous processing

#### Scenario: Valid GitHub webhook received and accepted

- **WHEN** a POST request is made to `/webhooks/github` with a valid `X-Hub-Signature-256` header and JSON body
- **THEN** the response status is 200, the body contains `{"status": "accepted"}`, and the payload is dispatched to the GitHub webhook handler

#### Scenario: Webhook for unknown source

- **WHEN** a POST request is made to `/webhooks/unknown` and no triggers exist with source="unknown"
- **THEN** the response status is 401 with body `{"detail": "No matching trigger"}`

## ADDED Requirements

### Requirement: Dispatch GitHub webhooks to handler

When the webhook receiver matches a trigger with `source: "github"`, the system SHALL dispatch the payload to `handle_github_webhook()` from `errand.platforms.github.handler`. The dispatch SHALL pass the parsed JSON payload, the matched `WebhookTrigger`, and a database session. This follows the same async dispatch pattern used for Jira webhooks.

#### Scenario: GitHub webhook dispatched to handler

- **WHEN** a webhook arrives at `/webhooks/github` and matches a trigger with `source: "github"`
- **THEN** the system calls `handle_github_webhook(payload, trigger, db)` as a background task

#### Scenario: GitHub source with no handler logs warning

- **WHEN** a webhook arrives and matches a trigger with an unrecognized source (not "jira" or "github")
- **THEN** the system logs a warning: "No handler for webhook source: {source}"
