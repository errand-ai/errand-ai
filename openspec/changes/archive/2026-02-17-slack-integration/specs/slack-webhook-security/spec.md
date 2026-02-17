## ADDED Requirements

### Requirement: Slack request signature verification
The system SHALL provide a FastAPI dependency in `backend/platforms/slack/verification.py` that verifies the authenticity of all inbound Slack requests using HMAC-SHA256 signature verification. The dependency SHALL read the `X-Slack-Signature` and `X-Slack-Request-Timestamp` headers from each request. The dependency SHALL reject requests older than 5 minutes (replay attack protection). The dependency SHALL compute `HMAC-SHA256(signing_secret, "v0:{timestamp}:{raw_body}")` and compare the result with the provided signature using `hmac.compare_digest` (timing-safe comparison). The signing secret SHALL be loaded from the Slack platform's encrypted credentials in the database.

#### Scenario: Valid Slack request
- **WHEN** a request arrives with a valid signature and timestamp within 5 minutes
- **THEN** the dependency passes and the request handler executes

#### Scenario: Invalid signature
- **WHEN** a request arrives with an incorrect `X-Slack-Signature` header
- **THEN** the dependency raises HTTP 403 with a message indicating signature verification failed

#### Scenario: Missing signature headers
- **WHEN** a request arrives without `X-Slack-Signature` or `X-Slack-Request-Timestamp` headers
- **THEN** the dependency raises HTTP 403

#### Scenario: Expired timestamp (replay attack)
- **WHEN** a request arrives with `X-Slack-Request-Timestamp` older than 5 minutes
- **THEN** the dependency raises HTTP 403 with a message indicating the request is too old

#### Scenario: Slack credentials not configured
- **WHEN** a Slack request arrives but no Slack credentials are stored in the database
- **THEN** the dependency raises HTTP 503 with a message indicating Slack is not configured

### Requirement: Slack Events API URL verification
The system SHALL handle the Slack Events API URL verification challenge at `POST /slack/events`. When a request contains `{"type": "url_verification", "challenge": "<value>"}`, the endpoint SHALL respond with `{"challenge": "<value>"}` and HTTP 200. This is required for initial Slack app setup. The URL verification request SHALL NOT require signature verification (Slack sends it before the signing secret is validated).

#### Scenario: URL verification challenge
- **WHEN** Slack sends a POST to `/slack/events` with `{"type": "url_verification", "challenge": "abc123"}`
- **THEN** the endpoint responds with `{"challenge": "abc123"}` and HTTP 200

#### Scenario: Non-verification event
- **WHEN** a POST to `/slack/events` does not contain `type: url_verification`
- **THEN** the request is processed through the normal signature verification pipeline
