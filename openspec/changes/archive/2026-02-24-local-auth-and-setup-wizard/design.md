## Context

Errand currently has two auth modes: full Keycloak SSO (when OIDC env vars are set) or anonymous admin (when they're missing). Settings are split across two disjoint systems — environment variables (read at import time) and the database `settings` table (managed via the UI). The macOS desktop app needs a middle ground: local user auth without an external IdP, and the ability to configure LLM and SSO settings through the UI rather than env vars.

## Goals / Non-Goals

**Goals:**

- Single-user local admin authentication with bcrypt password hashing and backend-minted JWTs
- Seamless auth mode detection: the frontend discovers the auth mode from the backend and presents the appropriate flow
- 3-step setup wizard for first-launch experience on desktop
- Unified settings model: every setting knows its source (env/DB/default) and the UI reflects this
- SSO configurable via the Settings UI (not just env vars)
- LLM provider URL/API key configurable via the UI
- Docker Compose auto-provisioning via `ADMIN_USERNAME`/`ADMIN_PASSWORD` env vars

**Non-Goals:**

- Multi-user local auth (single admin only for now)
- User self-registration
- Password reset flow (single admin can always access the DB directly)
- Migrating existing env-var-only settings to DB on upgrade (env vars remain as-is)
- OAuth2/social login (beyond OIDC SSO)

## Decisions

### 1. Auth mode resolution order

The backend determines auth mode at startup:

```
1. OIDC env vars set (OIDC_DISCOVERY_URL + CLIENT_ID + CLIENT_SECRET)?
   → SSO mode (env-locked, read-only in UI)
2. OIDC settings in DB (oidc_discovery_url + oidc_client_id + oidc_client_secret)?
   → SSO mode (DB-sourced, editable in UI)
3. Local admin user exists in local_users table?
   → Local auth mode (show login form)
4. ADMIN_USERNAME + ADMIN_PASSWORD env vars set?
   → Auto-create local admin, then local auth mode
5. None of the above?
   → Setup mode (show wizard)
```

**Alternative considered**: Explicit `AUTH_MODE` env var. Rejected because implicit detection is more "zero-config" for desktop users — the app figures it out.

### 2. Local auth uses backend-minted JWTs

When a local user logs in via `POST /auth/local/login`, the backend validates the password and mints a JWT with the same claims structure as OIDC tokens (`sub`, `email`, `_roles`). The frontend auth store doesn't need to know the difference — it just stores and sends the JWT.

The JWT is signed with an HMAC secret stored as a setting (`jwt_signing_secret`), auto-generated on first startup. Token expiry is 24 hours with no refresh (local single-user doesn't need short-lived tokens).

**Alternative considered**: Session-based auth with cookies. Rejected because it requires reworking the entire frontend auth system. JWTs keep the frontend unchanged.

### 3. Settings registry — metadata layer

The `GET /api/settings` response changes from flat `{key: value}` to `{key: {value, source, sensitive, readonly}}`:

```json
{
  "openai_api_key": {
    "value": "sk-****",
    "source": "env",
    "sensitive": true,
    "readonly": true
  },
  "llm_model": {
    "value": "claude-haiku-4-5-20251001",
    "source": "database",
    "sensitive": false,
    "readonly": false
  },
  "system_prompt": {
    "value": "You are a helpful...",
    "source": "database",
    "sensitive": false,
    "readonly": false
  }
}
```

A settings definition registry (Python dict) maps each known setting to its env var name (if any), sensitivity flag, and default value. At read time:

1. If the env var is set → use it, mark `source: "env"`, `readonly: true`
2. Else if the DB has a value → use it, mark `source: "database"`, `readonly: false`
3. Else → use default (if any), mark `source: "default"`, `readonly: false`

Sensitive values from env vars are masked in the response (show first 4 chars + `****`). Sensitive values from DB are shown in full to the admin (they entered them).

**Breaking change**: The `GET /api/settings` response format changes. The frontend settings page must be updated to handle the new structure.

### 4. OIDC config stored in DB

New settings keys: `oidc_discovery_url`, `oidc_client_id`, `oidc_client_secret`, `oidc_roles_claim`. When saved via the User Management settings page, these are stored in the DB `settings` table.

On startup, the backend checks env vars first, then DB. When the admin saves SSO config via the UI and clicks "Enable SSO", the backend hot-reloads: it runs OIDC discovery against the new config and switches to SSO mode without requiring a restart. The `/api/auth/status` endpoint reflects the new mode immediately.

If the admin later removes SSO config (deletes the settings), the system reverts to local auth on the next request to `/api/auth/status`.

**Risk**: Hot-reloading OIDC config mid-flight could break in-progress requests. Mitigated by using an atomic swap of the `oidc` module-level variable after successful discovery.

### 5. LLM provider config in DB

New settings keys: `openai_base_url`, `openai_api_key`. Resolution order: env var → DB → unconfigured.

The `get_llm_client()` function is refactored to check DB settings when env vars are absent. The worker also needs this resolution — it reads from the DB at task processing time (it already has a DB session).

The setup wizard's "LLM Provider" step saves these to the DB via `PUT /api/settings`, then the model list endpoint uses the newly configured client.

### 6. Setup wizard — unauthenticated first-user creation

`POST /api/setup/create-user` is an unauthenticated endpoint guarded by a check: if any row exists in `local_users`, return 403. This is the only unauthenticated write endpoint.

After the user is created, the wizard auto-logs in (the endpoint returns a JWT). Steps 2 and 3 of the wizard run authenticated.

### 7. `local_users` table — minimal schema

```python
class LocalUser(Base):
    __tablename__ = "local_users"
    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(Text, unique=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(Text, nullable=False)
    role: Mapped[str] = mapped_column(Text, default="admin", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), ...)
```

Single row, always admin. Uses `bcrypt` via `passlib` for password hashing.

### 8. Frontend boot sequence

```
App.vue onMounted:
  1. GET /api/auth/status → {mode, sso_login_url}
  2. Switch on mode:
     - "setup" → route to /setup (wizard)
     - "local" → show local login form (if no token)
     - "sso"  → check for token in fragment (OIDC callback)
                 or redirect to sso_login_url
```

The `authMode` is stored in the Pinia auth store so components can adapt (e.g., header shows "Log out" differently for local vs SSO users, login form vs SSO redirect).

## Risks / Trade-offs

- **Breaking API change on `GET /api/settings`** → Frontend must be updated in the same release. All settings components need to unwrap `{value, source, ...}` instead of using raw values.
- **Hot-reload OIDC could fail** → If discovery fails, the backend keeps the previous auth mode and returns an error to the UI. The admin can fix the config and retry.
- **JWT signing secret in DB** → If the DB is compromised, tokens can be forged. Acceptable for single-user desktop app. K8s deployments use SSO (OIDC) with external JWKS.
- **No password reset** → Single admin user. If the password is lost, the user can reset it via the DB directly (`UPDATE local_users SET password_hash = ...`). Acceptable for v1.
- **Worker needs DB access for LLM config** → The worker already reads settings from the DB (system prompt, MCP config, etc.), so this is consistent. No new dependency.
