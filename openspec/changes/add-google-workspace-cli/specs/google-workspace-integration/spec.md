## ADDED Requirements

### Requirement: gws CLI installed in task-runner image
The task-runner Dockerfile SHALL include a build stage that installs the Google Workspace CLI (`gws`) by downloading the pre-built release tarball from `github.com/googleworkspace/cli` (matching `${GWS_VERSION}` and the build's `TARGETARCH`) and copies the agent skill files from the same repository (cloned at the matching version tag) into `/opt/system-skills/gws/` in the final image. The `gws` binary SHALL be available at `/usr/local/bin/gws`.

#### Scenario: gws binary available in container
- **WHEN** the task-runner container starts
- **THEN** `gws --version` executes successfully and outputs a version string

#### Scenario: Skills bundled at build time
- **WHEN** the task-runner image is built
- **THEN** `/opt/system-skills/gws/` contains SKILL.md files for Google Workspace services (Drive, Gmail, Calendar, Sheets, Docs, etc.) sourced from the upstream `googleworkspace/cli` repository

#### Scenario: gws-shared skill present
- **WHEN** the task-runner image is built
- **THEN** `/opt/system-skills/gws/gws-shared/SKILL.md` exists with auth and security instructions

### Requirement: Google token injection via environment variable
The task manager SHALL inject the Google OAuth access token as the `GOOGLE_WORKSPACE_CLI_TOKEN` environment variable on the task-runner container when Google Workspace credentials exist and the token is valid.

#### Scenario: Google credentials exist and token is fresh
- **WHEN** the task manager prepares a task and Google Workspace credentials exist with a non-expired access token
- **THEN** the container is started with `GOOGLE_WORKSPACE_CLI_TOKEN` set to the access token value

#### Scenario: Google credentials exist but token expired
- **WHEN** the task manager prepares a task and Google Workspace credentials exist with an expired token
- **THEN** the task manager refreshes the token before injecting it as `GOOGLE_WORKSPACE_CLI_TOKEN`

#### Scenario: No Google credentials
- **WHEN** the task manager prepares a task and no Google Workspace credentials exist
- **THEN** the container is started without the `GOOGLE_WORKSPACE_CLI_TOKEN` environment variable

### Requirement: Conditional gws skill injection
The task manager SHALL include gws agent skills in the skills archive only when the `GOOGLE_WORKSPACE_CLI_TOKEN` environment variable is being injected for the task. When included, gws skills SHALL be merged with DB and git skills at the lowest precedence (DB > git > system).

#### Scenario: Google token present — skills included
- **WHEN** the task manager prepares a task with a valid Google token
- **THEN** gws skills are included in the `/workspace/skills/` directory alongside any DB and git skills
- **AND** the skill manifest in the system prompt lists the gws skills

#### Scenario: No Google token — skills excluded
- **WHEN** the task manager prepares a task without Google credentials
- **THEN** no gws skills are included in the skills archive

#### Scenario: DB skill name conflicts with gws skill
- **WHEN** a DB skill has the same name as a gws skill (e.g., "gws-drive")
- **THEN** the DB skill takes precedence and the gws skill is excluded

#### Scenario: Profile MCP filter does not affect gws skills
- **WHEN** a task profile has `_profile_mcp_servers` restrictions
- **THEN** gws skills are still included if Google token is present (skills are not MCP servers)

### Requirement: gws skills bundled in server image
The errand server Docker image SHALL include the gws agent skills at `/app/system-skills/gws/` so that `task_manager.py` can read them locally when building the skills archive. The skills SHALL be copied from the same generation step used in the task-runner image build, or generated separately in the server image build.

#### Scenario: Server reads system skills locally
- **WHEN** the task manager builds the skills archive and Google token is present
- **THEN** it reads gws SKILL.md files from `/app/system-skills/gws/` on the local filesystem

### Requirement: Expanded Google OAuth scopes
The Google OAuth authorization flow SHALL request scopes covering Drive, Gmail, Calendar, Sheets, Docs, Chat, Tasks, and Contacts in addition to OpenID Connect scopes.

#### Scenario: New authorization requests full scopes
- **WHEN** a user initiates Google Workspace authorization
- **THEN** the OAuth request includes scopes for `drive`, `gmail.modify`, `calendar`, `spreadsheets`, `documents`, `chat.messages`, `tasks`, and `contacts.readonly`

#### Scenario: Stale-scope detection
- **WHEN** the integration status endpoint is called and stored Google credentials have fewer scopes than currently required
- **THEN** the status response includes `"reauth_required": true`

#### Scenario: Re-authorization preserves refresh token
- **WHEN** a user re-authorizes with expanded scopes
- **THEN** the new refresh token replaces the old one and the stored scope list is updated
