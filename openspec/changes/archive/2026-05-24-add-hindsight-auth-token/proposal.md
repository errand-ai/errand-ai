## Why

Hindsight servers may sit behind an authenticating reverse proxy (e.g. an OAuth2/bearer-token gateway), in which case the MCP HTTP requests from the task-runner are rejected with `401 Unauthorized`. The current task-manager injection at `errand/task_manager.py:1535-1540` only passes the Hindsight MCP URL — no `Authorization` header — so there is no way to use a protected Hindsight deployment without disabling auth at the proxy.

We need to let operators configure a bearer token alongside the existing `hindsight_url` / `hindsight_bank_id` settings, and have the task-manager inject it as an `Authorization: Bearer <token>` header on the `hindsight` MCP server entry, matching the pattern already used for `litellm_*` and `onedrive`.

## What Changes

- Add a new admin setting `hindsight_token` (string, secret) and a matching `HINDSIGHT_TOKEN` environment variable, resolved with the same env-then-setting precedence already used for `hindsight_url` and `hindsight_bank_id`.
- When a non-empty token is resolved, the task-manager injects `headers: {"Authorization": "Bearer <token>"}` into the `hindsight` entry of the task-runner's `mcp.json`.
- When no token is resolved, behaviour is unchanged: the `hindsight` entry is injected with only a `url`.
- Token value is treated as a secret: never logged, never returned by `GET /api/settings` in plaintext (same redaction treatment as other secret settings), and not surfaced into the task-runner system prompt.
- Admin Settings UI exposes the new field under the existing Hindsight settings group as a password-style input.

## Capabilities

### New Capabilities

(none — extending an existing capability)

### Modified Capabilities

- `task-runner-memory`: add a `hindsight_token` setting + `HINDSIGHT_TOKEN` env var, and require the task-manager to inject an `Authorization: Bearer <token>` header on the `hindsight` MCP server entry when a token is resolved.

## Impact

- **Code**: `errand/task_manager.py` (settings load block ~`:701-750` + Hindsight MCP injection at `:1535-1540`), settings model / migrations if a new settings key needs registering, and the admin-settings frontend component that renders the Hindsight section.
- **Config**: New env var `HINDSIGHT_TOKEN` accepted by the server container; new row in the `settings` table keyed `hindsight_token`. Helm chart may optionally pipe a secret value through to the env var (no chart change strictly required — operators can set the env directly).
- **Tests**: `errand/tests/test_worker.py` Hindsight injection tests gain coverage for the header-present and header-absent paths.
- **Security**: New secret to manage; redaction logic in `GET /api/settings` must include the new key.
- **No breaking changes**: existing deployments without a token continue to work unchanged.
