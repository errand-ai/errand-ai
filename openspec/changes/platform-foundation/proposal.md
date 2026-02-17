## Why

The system currently has a single hard-coded `post_tweet` MCP tool with credentials managed via environment variables. To support multiple messaging platforms (Slack, LinkedIn, YouTube) as both publishing targets and interaction surfaces, a platform abstraction layer is needed. This also requires secure credential management (encrypted in DB, managed via UI) and task audit metadata to track who performed actions across multiple interaction surfaces.

## What Changes

- Introduce a `Platform` abstract base class defining the common interface for all messaging platforms, with a capability system declaring what each platform supports
- Introduce a `PlatformRegistry` for discovering and accessing configured platforms at runtime
- Add a `PlatformCredential` database model with Fernet-encrypted credential storage (AES-128-CBC + HMAC-SHA256)
- Add backend API endpoints for platform credential CRUD (admin-only), including connection verification
- Add a frontend platform settings UI for managing platform credentials with masked inputs and connection testing
- Add `created_by` and `updated_by` audit fields to the `Task` model, populated from JWT email (web UI) or platform user identity (Slack etc.)
- Update all task write endpoints (create, update, delete) to populate audit fields from the authenticated user
- Migrate the existing `post_tweet` MCP tool to use a `TwitterPlatform` class that implements the new abstraction, loading credentials from encrypted DB storage instead of environment variables
- **BREAKING**: Twitter credentials will move from environment variables to encrypted DB storage. Existing env var configuration will continue to work as a fallback during migration.

## Capabilities

### New Capabilities
- `platform-abstraction`: Base platform protocol, capability system, and platform registry
- `platform-credentials`: Encrypted credential storage model, Fernet encryption service, and credential CRUD API
- `platform-credentials-ui`: Frontend UI for managing platform credentials (settings page)
- `task-audit-metadata`: created_by/updated_by fields on Task model, populated across all interaction surfaces

### Modified Capabilities
- `twitter-posting`: Twitter posting migrated from hard-coded MCP tool to TwitterPlatform class using the platform abstraction; credentials loaded from encrypted DB with env var fallback
- `task-api`: Task API responses include created_by/updated_by fields; write endpoints populate them from authenticated user
- `mcp-server-endpoint`: MCP tools/list response reflects migrated twitter tool; post_tweet delegates to platform abstraction

## Impact

- **Backend**: New `backend/platforms/` package with base classes, registry, credential encryption, and Twitter implementation. New `PlatformCredential` model and Alembic migration. Task model migration for audit fields. New API routes for credential management. Modified task endpoints.
- **Frontend**: New platform settings view and components. Settings navigation updated.
- **Database**: Two Alembic migrations (PlatformCredential table, Task audit columns).
- **Dependencies**: `cryptography` package added to backend requirements (for Fernet).
- **Helm**: `CREDENTIAL_ENCRYPTION_KEY` env var added to backend and worker deployments (from K8s secret).
- **Deployment**: One-time credential migration from env vars to DB (can be a management command or done via UI).
