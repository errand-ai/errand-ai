## MODIFIED Requirements

### Requirement: Hindsight bearer token configuration

The system SHALL support configuring a bearer token for the Hindsight MCP endpoint via the admin setting `hindsight_token` and a matching `HINDSIGHT_TOKEN` environment variable. The token SHALL be resolved with environment-variable-first precedence, identical to the precedence used for `hindsight_url` and `hindsight_bank_id`. The token SHALL be marked sensitive in the settings registry: env-sourced values SHALL be masked in `GET /api/settings` responses (consistent with the existing treatment of `oidc_client_secret` and other sensitive env-sourced settings), the value SHALL never be written to task logs, and the token SHALL never be interpolated into the task-runner system prompt or any skill file.

When neither the environment variable nor the admin setting supplies a token, and a Hindsight URL is configured, the system SHALL generate a cryptographically random bearer, persist it as the `hindsight_token` setting, and use it thereafter. Generation SHALL happen once and SHALL NOT overwrite a token that is already present from either source. The generated value SHALL be handled exactly as a configured one: masked on read, absent from logs, and never placed in a prompt or skill file. The deployment SHALL supply the same value to the Hindsight service as `HINDSIGHT_API_TENANT_API_KEY`, with `HINDSIGHT_API_TENANT_EXTENSION` set to the built-in API-key tenant extension, so that the MCP endpoint is authenticated rather than open by default. Where the deployment also runs the Hindsight Control Plane, it SHALL supply the same value to it, since enabling the extension authenticates every Hindsight HTTP endpoint and not only the MCP one.

#### Scenario: Token marked sensitive and masked when env-sourced

- **WHEN** `HINDSIGHT_TOKEN` is set to `sk-abc1234567890` and `GET /api/settings` is called
- **THEN** the response entry for `hindsight_token` reports `sensitive: true` and `readonly: true`
- **AND** the response value is the masked placeholder produced by `mask_sensitive_value` (e.g. `sk-a****`), not the literal token

#### Scenario: Environment variable takes precedence

- **WHEN** `HINDSIGHT_TOKEN` is set to `env-token` and the admin setting `hindsight_token` is `db-token`
- **THEN** the worker uses `env-token`

#### Scenario: Falls back to admin setting

- **WHEN** `HINDSIGHT_TOKEN` is not set and the admin setting `hindsight_token` is `db-token`
- **THEN** the worker uses `db-token`

#### Scenario: No token configured

- **WHEN** neither `HINDSIGHT_TOKEN` nor the admin setting `hindsight_token` is set and a Hindsight URL is configured
- **THEN** the system generates a random bearer, persists it as the `hindsight_token` setting, and injects it as the `Authorization` header on the Hindsight MCP entry

#### Scenario: Generation is idempotent

- **WHEN** a token has already been generated and persisted, and the server restarts
- **THEN** the persisted token is reused
- **AND** no new token is generated

#### Scenario: Generation never overwrites a configured token

- **WHEN** the admin setting `hindsight_token` holds an operator-supplied value
- **THEN** no token is generated
- **AND** the operator-supplied value is used unchanged

#### Scenario: Generated token is masked on read

- **WHEN** a token has been generated and `GET /api/settings` is called
- **THEN** the value returned for `hindsight_token` is masked, exactly as a configured token would be
