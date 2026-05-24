## ADDED Requirements

### Requirement: Hindsight bearer token configuration

The system SHALL support configuring a bearer token for the Hindsight MCP endpoint via a new admin setting `hindsight_token` and a matching `HINDSIGHT_TOKEN` environment variable. The token SHALL be resolved with environment-variable-first precedence, identical to the precedence used for `hindsight_url` and `hindsight_bank_id`. The token SHALL be marked sensitive in the settings registry: env-sourced values SHALL be masked in `GET /api/settings` responses (consistent with the existing treatment of `oidc_client_secret` and other sensitive env-sourced settings), the value SHALL never be written to task logs, and the token SHALL never be interpolated into the task-runner system prompt or any skill file.

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

- **WHEN** neither `HINDSIGHT_TOKEN` nor the admin setting `hindsight_token` is set
- **THEN** the worker treats the token as empty and proceeds without injecting an `Authorization` header

## MODIFIED Requirements

### Requirement: Worker injects Hindsight MCP server for task runner

The worker SHALL inject a `hindsight` entry into the task runner's MCP server configuration when Hindsight is configured. The MCP server URL SHALL follow the single-bank pattern: `{hindsight_url}/mcp/{bank_id}/`. The injection SHALL follow the same pattern as existing MCP server injections (errand backend): inject only if not already present in the database-configured MCP servers. When a non-empty Hindsight bearer token is resolved (per the Hindsight bearer token configuration requirement), the injected entry SHALL additionally contain a `headers` dict with a single key `Authorization` whose value is the string `Bearer ` concatenated with the resolved token. When no token is resolved, the injected entry SHALL contain only the `url` field (no `headers` key) so that the entry shape is identical to the pre-token behaviour.

#### Scenario: Hindsight MCP server injected

- **WHEN** the worker processes a task with `HINDSIGHT_URL` set to `http://hindsight-api:8888` and bank ID `errand-tasks` and no Hindsight token configured
- **THEN** the MCP configuration includes `{"hindsight": {"url": "http://hindsight-api:8888/mcp/errand-tasks/"}}` with no `headers` key

#### Scenario: Database MCP config takes precedence

- **WHEN** the database MCP configuration already contains a `hindsight` entry
- **THEN** the worker SHALL NOT overwrite it with the injected entry

#### Scenario: System prompt includes memory instructions

- **WHEN** the worker injects the Hindsight MCP server
- **THEN** the worker SHALL append a memory usage instruction section to the system prompt instructing the agent that it has access to Hindsight memory tools (`retain`, `recall`, `reflect`) and should use them to store important learnings and recall relevant context

#### Scenario: Authorization header injected when token configured

- **WHEN** the worker processes a task with `HINDSIGHT_URL` set to `http://hindsight-api:8888`, bank ID `errand-tasks`, and a resolved Hindsight token of `sk-abc123`
- **THEN** the MCP configuration `hindsight` entry contains `"url": "http://hindsight-api:8888/mcp/errand-tasks/"` and `"headers": {"Authorization": "Bearer sk-abc123"}`

#### Scenario: No header injected when token is empty

- **WHEN** the worker processes a task with `HINDSIGHT_URL` configured and the resolved Hindsight token is an empty string
- **THEN** the injected `hindsight` MCP entry contains only the `url` field and no `headers` key
