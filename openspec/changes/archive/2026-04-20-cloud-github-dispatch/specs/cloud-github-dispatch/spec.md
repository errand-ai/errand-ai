## ADDED Requirements

### Requirement: Cloud-relayed GitHub webhook dispatch
The cloud dispatch module SHALL route GitHub webhook payloads received via the errand-cloud WebSocket relay to the GitHub webhook handler.

#### Scenario: GitHub webhook dispatched from cloud relay
- **WHEN** a relay message arrives with `integration="github"` and `endpoint_type="webhook"`
- **THEN** the dispatcher SHALL extract `trigger_id` from the message
- **THEN** the dispatcher SHALL load the `WebhookTrigger` matching the `trigger_id`
- **THEN** the dispatcher SHALL call `handle_github_webhook(trigger, body, headers)`

#### Scenario: Missing trigger_id
- **WHEN** a GitHub webhook relay message has no `trigger_id`
- **THEN** the dispatcher SHALL log a warning and discard the message

#### Scenario: Invalid trigger_id
- **WHEN** the `trigger_id` is not a valid UUID
- **THEN** the dispatcher SHALL log a warning and discard the message

#### Scenario: Trigger not found
- **WHEN** no `WebhookTrigger` exists for the given `trigger_id`
- **THEN** the dispatcher SHALL log a warning and discard the message

#### Scenario: Trigger disabled
- **WHEN** the matched trigger has `enabled=False`
- **THEN** the dispatcher SHALL log a warning and discard the message

### Requirement: HMAC re-verification for defense in depth
The dispatcher SHALL re-verify the HMAC signature of cloud-relayed GitHub webhooks before processing.

#### Scenario: Successful re-verification
- **WHEN** the trigger has a `webhook_secret` and the relay message headers contain `x-hub-signature-256`
- **THEN** the dispatcher SHALL decrypt the trigger's secret
- **THEN** the dispatcher SHALL verify the HMAC-SHA256 signature matches the body
- **THEN** on success, the dispatcher SHALL proceed to call the handler

#### Scenario: Re-verification failure
- **WHEN** the HMAC re-verification fails
- **THEN** the dispatcher SHALL log a warning and discard the message

#### Scenario: Missing signature header
- **WHEN** the trigger has a `webhook_secret` but the relay message has no `x-hub-signature-256` header
- **THEN** the dispatcher SHALL log a warning and discard the message

#### Scenario: Secret decryption failure
- **WHEN** the trigger's webhook secret cannot be decrypted
- **THEN** the dispatcher SHALL log a warning and discard the message
