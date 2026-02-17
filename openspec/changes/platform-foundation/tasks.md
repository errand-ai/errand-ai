## 1. Dependencies and project setup

- [x] 1.1 Add `cryptography` to `backend/requirements.txt`
- [x] 1.2 Rebuild backend venv: `backend/.venv/bin/pip install -r backend/requirements.txt`
- [x] 1.3 Bump VERSION file (minor version bump — new feature)

## 2. Database models and migrations

- [x] 2.1 Add `PlatformCredential` model to `backend/models.py` (platform_id PK, encrypted_data, status, last_verified_at, updated_at)
- [x] 2.2 Add `created_by` and `updated_by` columns to `Task` model in `backend/models.py`
- [x] 2.3 Create Alembic migration for `platform_credentials` table
- [x] 2.4 Create Alembic migration for `created_by`/`updated_by` columns on `tasks` table
- [x] 2.5 Test migrations run cleanly (upgrade and downgrade)

## 3. Platform abstraction layer

- [x] 3.1 Create `backend/platforms/__init__.py` with `PlatformRegistry` class (register, get, list_all, list_configured) and module-level `get_registry()` function
- [x] 3.2 Create `backend/platforms/base.py` with `Platform` ABC, `PlatformCapability` enum, `PlatformInfo` dataclass, and `PostResult` dataclass
- [x] 3.3 Write tests for `PlatformRegistry` (register, get, list_all, list_configured)

## 4. Credential encryption service

- [x] 4.1 Create `backend/platforms/credentials.py` with `encrypt()`, `decrypt()`, `load_credentials()` functions using Fernet
- [x] 4.2 Write tests for encrypt/decrypt round-trip, wrong key failure, missing key error
- [x] 4.3 Write tests for `load_credentials()` (credentials exist, credentials don't exist)

## 5. Twitter platform implementation

- [x] 5.1 Create `backend/platforms/twitter.py` with `TwitterPlatform` class implementing `Platform` ABC
- [x] 5.2 Implement `info()` returning PlatformInfo with credential_schema for Twitter's 4 credential fields
- [x] 5.3 Implement `verify_credentials()` making a test `client.get_me()` call
- [x] 5.4 Implement `post()` creating a tweet via Tweepy, with DB credentials → env var fallback
- [x] 5.5 Write tests for `TwitterPlatform` (info, verify_credentials, post with mocked Tweepy)

## 6. Platform credential API endpoints

- [x] 6.1 Add `GET /api/platforms` endpoint (list all platforms with config status, any authenticated user)
- [x] 6.2 Add `PUT /api/platforms/{platform_id}/credentials` endpoint (save + verify credentials, admin only)
- [x] 6.3 Add `GET /api/platforms/{platform_id}/credentials` endpoint (credential status, admin only)
- [x] 6.4 Add `DELETE /api/platforms/{platform_id}/credentials` endpoint (disconnect, admin only)
- [x] 6.5 Add `POST /api/platforms/{platform_id}/credentials/verify` endpoint (re-verify, admin only)
- [x] 6.6 Write tests for all credential API endpoints (valid/invalid/unauthorized scenarios)

## 7. Task audit metadata integration

- [x] 7.1 Update `POST /api/tasks` to extract email from JWT and set `created_by`
- [x] 7.2 Update `PATCH /api/tasks/{id}` to extract email from JWT and set `updated_by`
- [x] 7.3 Update `TaskResponse` Pydantic model to include `created_by` and `updated_by`
- [x] 7.4 Update worker to set `updated_by = "system"` when modifying tasks
- [x] 7.5 Write tests for audit field population (create, update, worker, API response)

## 8. MCP tool migration

- [x] 8.1 Refactor `post_tweet` in `mcp_server.py` to delegate to `registry.get("twitter").post()`
- [x] 8.2 Initialize platform registry in MCP server (or share with main app's registry)
- [x] 8.3 Update existing `post_tweet` tests to reflect delegation pattern
- [x] 8.4 Register `TwitterPlatform` in application lifespan startup

## 9. Frontend platform settings UI

- [x] 9.1 Create `PlatformSettings.vue` view with platform cards fetched from `GET /api/platforms`
- [x] 9.2 Create `PlatformCard.vue` component showing label, capabilities tags, connection status indicator
- [x] 9.3 Implement credential form with dynamic fields from `credential_schema`, masked password inputs with reveal toggle
- [x] 9.4 Implement "Test & Save" flow calling `PUT /api/platforms/{id}/credentials`
- [x] 9.5 Implement "Disconnect" flow with confirmation dialog calling `DELETE /api/platforms/{id}/credentials`
- [x] 9.6 Implement "Re-verify" button calling `POST /api/platforms/{id}/credentials/verify`
- [x] 9.7 Add "Platforms" navigation entry (admin-only visibility)
- [x] 9.8 Write frontend tests for PlatformSettings and PlatformCard components

## 10. Helm and deployment

- [x] 10.1 Add `CREDENTIAL_ENCRYPTION_KEY` env var to backend deployment template (from a K8s Secret)
- [x] 10.2 Add `CREDENTIAL_ENCRYPTION_KEY` env var to worker deployment template (same K8s Secret)
- [x] 10.3 Document key generation: `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"`

## 11. Integration testing and validation

- [x] 11.1 Run full backend test suite and fix any failures
- [x] 11.2 Run full frontend test suite and fix any failures
- [ ] 11.3 Test locally with `docker compose up --build` — verify platform settings UI, credential save/verify, tweet posting via MCP
