## Why

Errand now supports three deployment scenarios: Kubernetes (Helm), Docker Compose (local dev), and macOS desktop (errand-desktop with Apple Containers). The current auth model is binary — either full Keycloak SSO or no auth at all (anonymous admin). This doesn't work for the desktop app where there's no external identity provider, but users still need authentication. Additionally, settings like LLM provider URL/API key are only configurable via environment variables, making first-time setup for desktop users impossible through the UI.

## What Changes

- **Local authentication**: Add single-user local admin auth with password hashing and backend-minted JWTs. No more anonymous mode — the system always requires authentication (local or SSO).
- **Auth mode detection**: New unauthenticated `GET /api/auth/status` endpoint that returns the current auth mode (`setup`, `local`, or `sso`) so the frontend knows which login flow to present.
- **Setup wizard**: 3-step first-launch flow (create admin account → configure LLM provider → select models) that appears when no local admin exists and SSO is not configured.
- **Settings registry with env var awareness**: Backend exposes metadata about each setting — its source (env/database/default), whether it's sensitive, and whether it's read-only. Env vars are the source of truth when set; they lock the corresponding setting in the UI.
- **LLM provider config in database**: `OPENAI_BASE_URL` and `OPENAI_API_KEY` can be stored in the settings table (via wizard or settings page), with resolution order: env var → database → unconfigured.
- **User Management settings tab**: New settings sub-page for managing auth mode — toggle between local auth and SSO by entering OIDC provider details. SSO config stored in DB takes effect on next startup (or hot-reloaded if feasible).
- **Docker Compose auto-provisioning**: `ADMIN_USERNAME` and `ADMIN_PASSWORD` env vars auto-create a local admin on startup, skipping the wizard for automated testing.

## Capabilities

### New Capabilities

- `local-auth`: Local single-user admin authentication with password hashing, JWT minting, login/logout endpoints
- `auth-mode-detection`: Unauthenticated endpoint to discover current auth mode, frontend boot sequence that routes to appropriate login flow or setup wizard
- `setup-wizard`: 3-step first-launch configuration wizard (account creation, LLM provider, model selection)
- `settings-registry`: Backend metadata layer that tracks setting source (env/database/default), sensitivity, and read-only status; frontend displays accordingly
- `user-management-settings`: Settings sub-page for auth mode management (local auth ↔ SSO toggle, OIDC configuration, password change)

### Modified Capabilities

- `keycloak-auth`: OIDC env vars are no longer required at startup — SSO config can also come from database settings. OIDC discovery happens from either source. Backend no longer fails to start when OIDC vars are missing.
- `frontend-auth`: App.vue boot sequence calls `/api/auth/status` first instead of blindly redirecting to OIDC. New local login form and setup wizard routes. Auth store gains `authMode` state.
- `admin-settings-api`: `GET /api/settings` response includes metadata (source, sensitive, readonly) per setting. New settings for OIDC config and LLM provider stored in DB. Settings resolution: env → DB → default.
- `admin-settings-ui`: Settings fields show read-only indicators for env-sourced values. Sensitive values masked. New "User Management" sidebar entry.
- `settings-navigation`: New "User Management" sidebar link added to settings navigation.
- `app-navigation`: Header adapts based on auth mode — shows username for local auth, SSO user display for OIDC.
- `llm-integration`: LLM client initialization reads from DB settings if env vars are not set. Hot-reloadable when config changes via settings page.
- `local-dev-environment`: Docker Compose adds `ADMIN_USERNAME` and `ADMIN_PASSWORD` env vars to auto-provision local admin.

## Impact

- **Database**: New `local_users` table (Alembic migration). New settings keys for OIDC config (`oidc_discovery_url`, `oidc_client_id`, `oidc_client_secret`, `oidc_roles_claim`) and LLM provider (`openai_base_url`, `openai_api_key`).
- **Backend auth**: Complete rework of auth mode resolution in `lifespan()` and `get_current_user()`. New local auth endpoints. Anonymous mode removed.
- **Frontend**: New routes (`/setup/*`, `/login`), new components (setup wizard steps, local login form, user management settings). `App.vue` boot sequence rewritten.
- **Worker**: Must resolve `OPENAI_BASE_URL`/`OPENAI_API_KEY` from DB when env vars are unset.
- **Security**: Unauthenticated endpoint (`/api/auth/status`) exposes only auth mode. Create-first-user endpoint guarded to only work when zero users exist.
- **Docker Compose**: New env vars for auto-provisioning.
- **Helm chart**: No changes required (OIDC env vars still passed as before; they take precedence).
