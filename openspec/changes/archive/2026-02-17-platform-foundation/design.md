## Context

The system currently has a single hard-coded `post_tweet` function in `mcp_server.py` that reads four Twitter env vars and calls the Tweepy API directly. There is no abstraction for messaging platforms, no secure credential management beyond env vars, and no tracking of who creates or modifies tasks.

The system needs to support multiple platforms (Slack, Twitter, LinkedIn, YouTube) as both publishing targets and interaction surfaces. This change lays the foundation: a platform abstraction, encrypted credential storage, a credential management UI, and task audit metadata.

Existing infrastructure: FastAPI backend, SQLAlchemy + Alembic for DB, Pinia + Vue 3 frontend, Keycloak OIDC auth with JWT, Helm chart for K8s deployment.

## Goals / Non-Goals

**Goals:**
- Define a `Platform` protocol that all messaging platforms implement
- Provide encrypted credential storage that is secure at rest and easy to manage via UI
- Add audit metadata to tasks (who created/updated) for accountability across interaction surfaces
- Migrate Twitter to the new abstraction as a validation that the pattern works
- Keep the env var path working as a fallback for Twitter during migration

**Non-Goals:**
- Implementing Slack or any other platform beyond Twitter (separate change)
- Interactive UI elements (Block Kit buttons/modals) — that's a future change
- OAuth flows for platforms (LinkedIn, YouTube use OAuth, but that's Phase 2)
- Platform analytics or monitoring capabilities
- Multi-account per platform support (one account per platform is sufficient for now)

## Decisions

### 1. Platform protocol as Python ABC, not duck typing

**Decision:** Use `abc.ABC` with `@abstractmethod` for required methods and regular methods with `NotImplementedError` for capability-gated optional methods.

**Rationale:** ABCs give IDE autocompletion, clear error messages when a method isn't implemented, and make the contract explicit. Duck typing with Protocol would be lighter but gives worse error messages at runtime.

**Alternative considered:** Python `Protocol` (structural typing) — rejected because we want runtime registration and isinstance checks in the registry.

### 2. Capability enum on the platform, not separate mixin classes

**Decision:** Each platform declares a `set[PlatformCapability]` and the registry/callers check capabilities before invoking optional methods.

**Rationale:** Simpler than mixin-based composition. A platform that declares `{POST, MEDIA}` clearly communicates what it supports. Callers do `if PlatformCapability.POST in platform.capabilities` before calling `platform.post()`.

**Alternative considered:** Mixin classes (PostablePlatform, MediaPlatform, etc.) — rejected as over-engineered for 4-6 platforms. Would revisit if the platform count grows significantly.

### 3. Fernet symmetric encryption for credentials

**Decision:** Use `cryptography.fernet.Fernet` with a single master key from `CREDENTIAL_ENCRYPTION_KEY` env var.

**Rationale:** Fernet provides authenticated encryption (AES-128-CBC + HMAC-SHA256), is the Python Cryptographic Authority's recommended approach for symmetric encryption, includes timestamps for rotation, and is simple to use. The master key is a single env var shared by all pods.

**Alternative considered:**
- Envelope encryption (KMS-wrapped DEKs) — overkill for this scale, adds cloud provider dependency
- HashiCorp Vault — excellent but adds operational complexity and a new dependency
- Storing in K8s Secrets directly — requires K8s API access from pods and pod restarts for credential changes

### 4. Dedicated PlatformCredential model, not reusing Setting

**Decision:** Create a `PlatformCredential` table with `platform_id` (PK), `encrypted_data` (Text), `status`, `last_verified_at`, `updated_at`.

**Rationale:** Credentials have different access patterns and security requirements than general settings. They need encryption, verification status tracking, and should never be returned in plaintext from any API. A dedicated model makes this separation explicit.

**Alternative considered:** Using the existing `Setting` model with a naming convention (e.g., `platform:twitter:credentials`) — rejected because it would require special-casing credential keys throughout the settings API to avoid leaking encrypted blobs.

### 5. Email as the universal user identifier for audit fields

**Decision:** Store `created_by` and `updated_by` as email addresses (text) on the Task model. Web UI extracts email from JWT `email` claim. Slack resolves email via `users.info` API. System-initiated actions use `"system"`.

**Rationale:** Email is the natural join key between Keycloak and Slack. It's human-readable in the UI and database. Both Keycloak JWTs and Slack user profiles contain email addresses.

**Alternative considered:**
- Keycloak `sub` (UUID) — opaque, requires lookups to display
- Separate User model with foreign keys — adds schema complexity for a simple audit trail
- Username — not guaranteed unique across identity providers

### 6. Credential schema defined per platform, drives frontend form rendering

**Decision:** Each Platform class exposes a `credential_schema` property returning a dict describing required credential fields (name, type, label, help text). The frontend renders the form dynamically from this schema.

**Rationale:** The frontend doesn't need platform-specific knowledge. Adding a new platform automatically gets a credential management form. This is the same pattern as openclaw's `ChannelConfigSchema`.

### 7. Twitter env var fallback during migration

**Decision:** `TwitterPlatform` checks encrypted DB credentials first, falls back to env vars if no DB credentials exist.

**Rationale:** Avoids a hard cutover. Existing deployments continue working. Users can migrate to DB credentials at their own pace via the new UI.

## Risks / Trade-offs

- **[Master key management]** → If `CREDENTIAL_ENCRYPTION_KEY` is lost, all stored credentials become unrecoverable. Mitigation: document key backup procedures; the key is in a K8s Secret that should be backed up.
- **[Key rotation complexity]** → Changing the encryption key requires re-encrypting all credentials. Mitigation: build a key rotation utility from the start (decrypt with old key, encrypt with new key, update all rows).
- **[Slack email scope]** → Slack's `users:read.email` scope requires the Slack app to be installed with that scope. If an existing Slack app doesn't have it, re-installation is needed. Mitigation: document required scopes clearly (this applies to the follow-on slack-integration change, but the audit design depends on it).
- **[Nullable audit fields]** → Existing tasks won't have created_by/updated_by. Mitigation: fields are nullable; UI shows "Unknown" for null values.

## Migration Plan

1. Add `cryptography` to `backend/requirements.txt`
2. Run Alembic migration for `PlatformCredential` table
3. Run Alembic migration for Task audit columns (`created_by`, `updated_by`)
4. Deploy with `CREDENTIAL_ENCRYPTION_KEY` env var set (generate via `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"`)
5. Existing Twitter env vars continue working via fallback
6. Admin configures Twitter credentials via new UI → stored encrypted in DB
7. Once DB credentials verified, Twitter env vars can be removed from deployment
