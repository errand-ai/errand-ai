## Why

The task-runner currently accesses Google Drive via a dedicated MCP server container (`gdrive-mcp`). Google has released the Google Workspace CLI (`gws`) — a single binary providing full command-line access to all Google Workspace services (Drive, Gmail, Calendar, Sheets, Docs, Chat, and more). The CLI ships with agent skills in `SKILL.md` format, which is identical to the skill format the task-runner already supports.

By installing `gws` in the task-runner image and injecting the existing Google OAuth token via environment variable, we can replace the separate `gdrive-mcp` container while giving agents access to the entire Google Workspace — not just Drive. This also provides Gmail users an alternative to the current IMAP/SMTP-based email integration for in-task email operations.

The Settings UI also needs restructuring: Google Drive should move out of "Cloud Storage" into a new "Google Workspace" section on the Integrations page.

**Prerequisite:** The `task-generators-page` change must be merged first (it extracts email task-generation settings into a separate page and refactors the email poller).

## What Changes

- **Install `gws` CLI in the task-runner Docker image** with build-time skill generation via `gws generate-skills` (fetches current Google Discovery API specs)
- **Remove `gdrive-mcp` container/service** from docker-compose files, Helm chart (deployment, service), and all related env vars
- **Inject Google token as `GOOGLE_WORKSPACE_CLI_TOKEN` env var** on task-runner containers instead of MCP header injection, conditional on user having connected Google
- **Inject gws skills into the task-runner skills archive** conditionally (only when Google token is present)
- **Expand Google OAuth scopes** beyond `drive` to include Gmail, Calendar, and other Workspace services; existing users prompted to re-authorize
- **Restructure Settings → Integrations page**: move Google Drive out of "Cloud Storage" into a new "Google Workspace" section showing all available services

## Capabilities

### New Capabilities

- `google-workspace-integration`: Google Workspace CLI installation in task-runner image, build-time skill generation, conditional skill injection, and token injection via environment variable
- `google-workspace-settings-ui`: Settings UI section for Google Workspace showing connection status and available services (Drive, Gmail, Calendar, Sheets, Docs, etc.)

### Modified Capabilities

- `cloud-storage-worker-injection`: Remove Google Drive MCP injection; Google access now provided via `gws` CLI with `GOOGLE_WORKSPACE_CLI_TOKEN` env var and conditional skill injection instead of MCP server
- `cloud-storage-helm`: Remove `gdrive-mcp` Deployment, Service, and related env vars from Helm templates; Google Drive secrets still needed for OAuth but no longer for MCP server
- `cloud-storage-ui`: Remove Google Drive from the cloud storage cards; Google moves to its own "Google Workspace" section
- `cloud-storage-oauth`: Expand Google OAuth scopes to cover Workspace services beyond Drive; detect stale-scope tokens and prompt re-authorization
- `task-runner-image`: Add `gws` CLI binary and generated skills to the Docker image build
- `agent-skill-loading`: Support system-level skills baked into the task-runner image at `/opt/system-skills/`, merged with DB and git skills at injection time (system skills lowest precedence)

## Impact

- **Docker**: task-runner Dockerfile gains `gws` CLI build stage; `gdrive-mcp` removed from docker-compose files
- **Helm**: `gdrive-mcp-deployment.yaml` and `gdrive-mcp-service.yaml` deleted; server deployment env vars updated
- **Backend**: `task_manager.py` changes for token injection and system skill loading; `integration_routes.py` scope expansion
- **Frontend**: Integrations page restructured (new Google Workspace section, Google Drive removed from Cloud Storage)
- **OAuth**: Existing Google users need re-authorization after scope expansion
- **Breaking**: `GDRIVE_MCP_URL` env var no longer used; deployments referencing it need updating
