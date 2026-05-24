## Context

The task-manager injects an MCP server entry named `hindsight` into the task-runner's `mcp.json` whenever a Hindsight URL is configured (`errand/task_manager.py:1535-1540`). The entry currently contains only a `url`. The MCP client used by the task-runner already supports a `headers` dict on remote MCP entries — this is how both the `litellm_*` servers and the `onedrive` server pass `Authorization: Bearer …` today (`task_manager.py:1558-1567`, `:1577-1580`).

Hindsight itself is increasingly deployed behind authenticating reverse proxies (e.g. an OAuth2 proxy in front of a multi-tenant hosted Hindsight instance). For those deployments, MCP requests without an `Authorization` header are rejected with `401`, leaving Hindsight integration unusable.

The fix is a localised wiring change: introduce one new secret setting (`hindsight_token`) plus matching env var (`HINDSIGHT_TOKEN`), resolve it alongside the existing `hindsight_url` / `hindsight_bank_id` values, and add a `headers` dict when the token is non-empty.

## Goals / Non-Goals

**Goals:**
- Allow operators to configure a bearer token used as `Authorization: Bearer <token>` on every MCP request to Hindsight from the task-runner.
- Preserve existing zero-config behaviour: deployments that do not set a token must continue to work unchanged, and the entry shape stays minimal (no `headers` key) when no token is set.
- Treat the token as a secret: env-var-first precedence, redaction in `GET /api/settings`, password-style input in the admin UI, no leakage into the task-runner system prompt or task logs.

**Non-Goals:**
- No support for non-bearer auth schemes (Basic, mTLS, custom header names). If those are needed later they can be added as additional fields.
- No automatic token refresh / OAuth2 client-credentials flow inside errand. The token is treated as an opaque, long-lived bearer; rotating it is an operator action (update setting or env var → restart).
- No change to the server-side Hindsight prefetch path — it was already removed (`system-skill-hindsight` spec); there is no server-to-Hindsight HTTP call to authenticate. Only the task-runner-to-Hindsight MCP traffic gains an auth header.
- No change to the Helm chart in this change. Operators wiring a K8s Secret to `HINDSIGHT_TOKEN` can already do so via the existing `extraEnv` / `envFrom` patterns; chart-native support can come later if needed.

## Decisions

**Token delivered via MCP `headers`, not URL embedding.** The MCP client supports a `headers` dict on remote entries; this is the same mechanism already used for `litellm` and `onedrive`. Alternative considered: embed `?token=…` in the URL — rejected because (a) it leaks into proxy access logs, (b) Hindsight's auth proxy expects a header, not a query string, and (c) it diverges from the convention established by litellm/onedrive.

**Env var takes precedence over DB setting.** Matches the existing precedence applied to `hindsight_url` and `hindsight_bank_id` in `task_manager.py:1514-1518`. Keeps a single mental model for Hindsight config and lets K8s deployments inject a token from a `Secret` via `env` without ever writing the value to the database.

**Single bearer token, fixed `Authorization` header name.** Hindsight's documented auth model is bearer-token. Adding a header-name knob would invite mis-configuration and YAGNI. If a future Hindsight deployment requires a different scheme we can add an explicit setting at that point.

**No `headers` key when token is empty.** Keeps the injected entry byte-identical to today's shape in the unauthenticated case. This makes the change a strict superset of current behaviour and makes the existing injection-shape tests easy to keep green.

**Reuse existing secret-redaction path in `GET /api/settings`.** The settings endpoint already redacts known-secret keys (e.g. OAuth client secrets). Add `hindsight_token` to that list rather than inventing a new redaction mechanism. Writes via `PUT /api/settings` continue to accept the plaintext value.

## Risks / Trade-offs

- **Risk:** Token logged inadvertently via debug prints or stack traces in the task-manager. → **Mitigation:** Token is only read into a local variable and placed into the `headers` dict; no `logger.info(... token ...)` call is added. Existing structured-logging conventions don't dump the assembled `mcp.json`.
- **Risk:** Token leaks into the task-runner system prompt or skill files. → **Mitigation:** The injection is confined to `mcp.json` (an in-container file the runner reads only to wire up MCP clients). The `hindsight` system skill and prompt assembly do not interpolate any auth values.
- **Risk:** Existing tests that snapshot the injected `hindsight` entry shape break. → **Mitigation:** Default path keeps the entry shape unchanged; add new tests for the token-present path rather than mutating existing assertions.
- **Trade-off:** Rotating the token requires a server restart (env-var path) or a settings update + restart of in-flight runners is not in scope (DB-setting path). Acceptable — Hindsight tokens are long-lived.

## Migration Plan

1. Ship the code change. Existing deployments are unaffected: no token configured → no `headers` key → identical MCP entry as today.
2. Operators who need auth set `HINDSIGHT_TOKEN` on the server `Deployment` (or write `hindsight_token` via `PUT /api/settings`), restart the server, and verify task-runner tasks can reach Hindsight.
3. Rollback: clear the env var / unset the DB setting and restart. Behaviour reverts to pre-change.

## Open Questions

- None blocking. Operator-facing docs for configuring a token (env-var vs setting) can be added to `CLAUDE.md` / a future runbook entry after the change lands.
