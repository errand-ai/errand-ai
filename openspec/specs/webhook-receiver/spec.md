## ADDED Requirements

### Requirement: Webhook receiver HTTP endpoint

The system SHALL expose a `POST /webhooks/{source}` endpoint (e.g. `/webhooks/jira`, `/webhooks/github`) that receives incoming webhook payloads from external services. The endpoint SHALL NOT require authentication — it relies on HMAC signature verification instead. The endpoint SHALL return 200 immediately after validation and process the webhook asynchronously via a background task.

#### Scenario: Valid webhook received and accepted

- **WHEN** a POST request is made to `/webhooks/jira` with a valid HMAC signature and JSON body
- **THEN** the response status is 200, the body contains `{"status": "accepted"}`, and the payload is queued for asynchronous processing

#### Scenario: Webhook for unknown source

- **WHEN** a POST request is made to `/webhooks/unknown` and no triggers exist with source="unknown"
- **THEN** the response status is 401 with body `{"detail": "No matching trigger"}`

### Requirement: Direct-path HMAC signature verification

For webhooks received directly (not via cloud relay), the receiver SHALL extract the signature header from the request using a source-specific header name (e.g. Jira uses `X-Hub-Signature`). The receiver SHALL load all enabled triggers for the given source. For each trigger that has a `webhook_secret` configured, the receiver SHALL compute an HMAC-SHA256 digest of the raw request body using the trigger's secret and compare it to the provided signature. The first trigger whose secret produces a matching signature SHALL be selected as the matched trigger. If no trigger matches, the receiver SHALL return 401.

#### Scenario: Signature matches first trigger

- **WHEN** a webhook arrives at `/webhooks/jira` with header `X-Hub-Signature: sha256=abc123`, and the first enabled Jira trigger's secret produces a matching HMAC
- **THEN** that trigger is selected and the payload is processed using its configuration

#### Scenario: Signature matches second trigger

- **WHEN** two enabled Jira triggers exist and the first trigger's HMAC does not match but the second trigger's HMAC matches
- **THEN** the second trigger is selected

#### Scenario: No trigger signature matches

- **WHEN** a webhook arrives and no enabled trigger's secret produces a matching HMAC for the provided signature
- **THEN** the response status is 401 with body `{"detail": "No matching trigger"}`

#### Scenario: Trigger without secret is skipped during matching

- **WHEN** an enabled trigger has webhook_secret=null
- **THEN** that trigger is skipped during HMAC verification (it cannot match a signed request)

### Requirement: Cloud relay path

For webhooks received via the cloud relay (through `cloud_dispatch.py`), the relay message SHALL include `integration` (source name) and `trigger_id` fields. The receiver SHALL load the specific trigger by `trigger_id`. The receiver SHALL re-verify the HMAC signature against the trigger's secret for defense in depth. If the trigger does not exist, is disabled, or HMAC verification fails, the receiver SHALL log a warning and discard the message.

#### Scenario: Cloud relay with valid trigger

- **WHEN** a relay message arrives with integration="jira", trigger_id=<uuid>, and a valid HMAC signature
- **THEN** the specific trigger is loaded by ID, HMAC is re-verified, and the payload is processed

#### Scenario: Cloud relay with deleted trigger

- **WHEN** a relay message arrives with a trigger_id that no longer exists in the database
- **THEN** the receiver logs a warning "Trigger {trigger_id} not found, discarding relay message" and discards the message

#### Scenario: Cloud relay with disabled trigger

- **WHEN** a relay message arrives for a trigger that exists but has enabled=false
- **THEN** the receiver logs a warning and discards the message

### Requirement: Event deduplication

The receiver SHALL maintain a TTL cache of recently processed event IDs with a 5-minute expiry. The event ID SHALL be extracted from the payload using a source-specific method (e.g. Jira provides a webhook ID in the headers, GitHub provides `X-GitHub-Delivery`). If an event ID has been seen within the TTL window, the receiver SHALL return 200 without processing (idempotent). If the event ID is new, the receiver SHALL add it to the cache and proceed with processing.

#### Scenario: First delivery of an event

- **WHEN** a webhook arrives with event ID "evt-001" and the cache does not contain "evt-001"
- **THEN** "evt-001" is added to the cache and the payload is processed

#### Scenario: Duplicate delivery within TTL

- **WHEN** a webhook arrives with event ID "evt-001" and the cache already contains "evt-001" (within 5 minutes)
- **THEN** the response status is 200 with body `{"status": "duplicate"}` and no processing occurs

#### Scenario: Redelivery after TTL expiry

- **WHEN** a webhook arrives with event ID "evt-001" and the cache entry for "evt-001" has expired (older than 5 minutes)
- **THEN** the event is treated as new — added to the cache and processed

### Requirement: Source-specific header extraction

The receiver SHALL use a pluggable mechanism for extracting source-specific headers (signature header name, event ID header). Each source SHALL register its header mapping. The extraction MUST support at least the following sources:

| Source | Signature header | Event ID header |
|--------|-----------------|-----------------|
| jira | `X-Hub-Signature` | `X-Atlassian-Webhook-Identifier` |
| github | `X-Hub-Signature-256` | `X-GitHub-Delivery` |

#### Scenario: Jira headers extracted

- **WHEN** a webhook arrives at `/webhooks/jira`
- **THEN** the receiver reads the signature from `X-Hub-Signature` and the event ID from `X-Atlassian-Webhook-Identifier`

#### Scenario: GitHub headers extracted

- **WHEN** a webhook arrives at `/webhooks/github`
- **THEN** the receiver reads the signature from `X-Hub-Signature-256` and the event ID from `X-GitHub-Delivery`

### Requirement: Asynchronous processing via background task

After signature verification and deduplication, the receiver SHALL dispatch payload processing as an asyncio background task (using `asyncio.create_task` or FastAPI's `BackgroundTasks`). The endpoint SHALL return 200 before processing completes. Processing errors in the background task SHALL be logged but MUST NOT affect the HTTP response.

#### Scenario: Slow processing does not block response

- **WHEN** a valid webhook is received and processing takes 10 seconds
- **THEN** the HTTP response is returned within milliseconds and processing continues in the background

#### Scenario: Background processing error is logged

- **WHEN** a background task raises an exception during payload processing
- **THEN** the error is logged with the trigger_id, source, and event ID context, and the background task terminates cleanly
