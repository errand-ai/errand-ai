## 1. Version bump

- [x] 1.1 Bump `VERSION` (PATCH — backwards-compatible additive change)

## 2. Backend: settings & resolution

- [x] 2.1 Add `hindsight_token` to the default settings block / loader in `errand/task_manager.py` (around `:701-750`) alongside `hindsight_url` and `hindsight_bank_id`, defaulting to `""`
- [x] 2.2 In the per-task config resolution (around `:1513-1518`), read the token as `os.environ.get("HINDSIGHT_TOKEN", "") or settings.get("hindsight_token", "")`, mirroring the precedence used for URL and bank ID
- [x] 2.3 Add `hindsight_token` to the secret-redaction allow-list used by `GET /api/settings` so the plaintext value is never returned in API responses
    - Done via `settings_registry.SETTINGS_REGISTRY` entry `{"env_var": "HINDSIGHT_TOKEN", "sensitive": True, "default": ""}` — env-sourced values are masked by the existing `resolve_settings` path. DB-sourced sensitive values follow the pre-existing pattern (returned plaintext to admins, same as `oidc_client_secret` and `mcp_api_key`).
- [x] 2.4 If a new settings row needs to be registered (default-row insertion or migration), add the required Alembic migration under `errand/alembic/versions/`
    - Not required: the `settings` table stores arbitrary key/value rows; no schema change needed. `hindsight_url` and `hindsight_bank_id` already work without dedicated migrations.

## 3. Backend: MCP injection

- [x] 3.1 In the Hindsight MCP injection block (`errand/task_manager.py:1535-1540`), build the entry as `{"url": "<hindsight_url>/mcp/<bank_id>/"}` and conditionally add `"headers": {"Authorization": f"Bearer {hindsight_token}"}` only when the resolved token is truthy
- [x] 3.2 Preserve the existing "do not overwrite database-configured `hindsight` entry" behaviour
- [x] 3.3 Audit nearby `logger.*` and debug `print` calls to confirm the token value is never logged; do not add new log lines that include the assembled `mcp.json`
    - Verified: `hindsight_token` is only assigned to a local variable and placed into the `headers` dict. It is NOT added to `system_skill_context` (which only carries `hindsight_url`). No log line interpolates the token.

## 4. Frontend: admin settings UI

- [ ] 4.1 Add a `hindsight_token` field to the Hindsight section of the admin Settings page, rendered as a password-style input (`<input type="password">`) with the existing `***` placeholder pattern used for other secrets
- [ ] 4.2 Wire the field to the existing settings store / `PUT /api/settings` save path (no special handling beyond what the other secret settings already use)
    - **Deferred**: there is no existing Hindsight section in the frontend Settings page today (Hindsight has been configured exclusively via `HINDSIGHT_URL` / `HINDSIGHT_BANK_ID` env vars or direct DB writes). Adding a UI section is a separate, larger piece of work; the token can be configured today via `HINDSIGHT_TOKEN` env var (preferred for K8s deployments) or by `PUT /api/settings` with `{"hindsight_token": "..."}`.

## 5. Tests

- [x] 5.1 In `errand/tests/test_worker.py`, add a test asserting that when `HINDSIGHT_TOKEN` is set the injected `hindsight` MCP entry contains `headers: {"Authorization": "Bearer <token>"}` alongside the existing `url`
    - `test_hindsight_authorization_header_injected_when_token_configured`
- [x] 5.2 Add a test asserting that when no token is set the injected `hindsight` entry contains only the `url` field (no `headers` key)
    - `test_hindsight_no_authorization_header_when_token_empty`
- [x] 5.3 Add a test asserting that `HINDSIGHT_TOKEN` (env) takes precedence over the `hindsight_token` admin setting
    - `test_hindsight_token_env_var_takes_precedence_over_setting` + `test_hindsight_token_falls_back_to_admin_setting`
- [x] 5.4 Add a test asserting that `GET /api/settings` redacts the `hindsight_token` value (the plaintext is not present in the response payload)
    - `test_hindsight_token_masked_when_env_sourced` in `test_settings_registry.py` — env-sourced sensitive values are masked (matching existing pattern for `oidc_client_secret`).
- [x] 5.5 Confirm existing Hindsight injection tests (e.g. `test_hindsight_mcp_injected_when_configured`) still pass unchanged on the no-token path

## 6. Verification

- [x] 6.1 Run `errand/.venv/bin/python -m pytest errand/tests/test_worker.py -v` and confirm all Hindsight-related tests pass
- [x] 6.2 Run the full backend test suite: `DATABASE_URL="sqlite+aiosqlite:///:memory:" errand/.venv/bin/python -m pytest errand/tests/ -v`
    - 1628 passed.
- [ ] 6.3 Run `docker compose -f testing/docker-compose.yml up --build`, configure a Hindsight URL + token via the admin UI, trigger a task, and confirm the task-runner's `mcp.json` contains the `Authorization` header (inspect via `docker exec` into a running runner or via a log line in a dev-only debug branch)
- [ ] 6.4 Confirm `GET /api/settings` from the running stack does not return the plaintext token
    - **Deferred**: end-to-end runtime verification is left to the next session before merging the PR (per the project's "Verify the PR deployment before merging" rule in `CLAUDE.md`).
