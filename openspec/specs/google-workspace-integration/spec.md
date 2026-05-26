## Purpose

Bundles the Google Workspace CLI (`gws`) into the task-runner and errand server images and provides agent skills + token injection so connected users can drive Drive, Gmail, Calendar, Sheets, Docs, Chat, Tasks, and Contacts from inside a task. Replaces the previous `gdrive-mcp` sidecar.

## Requirements

### Requirement: gws CLI installed in task-runner image
The task-runner Dockerfile SHALL include a build stage that installs the Google Workspace CLI (`gws`) by downloading the pre-built `*-unknown-linux-musl` release tarball from `github.com/googleworkspace/cli` (matching `${GWS_VERSION}` and the build's `TARGETARCH`) and copies the agent skill files from the same repository (cloned at the matching version tag) into `/opt/system-skills/gws/` in the final image. The `gws` binary SHALL be available at `/usr/local/bin/gws`.

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
The task manager SHALL inject the Google OAuth access token as the `GOOGLE_WORKSPACE_CLI_TOKEN` environment variable on the task-runner container when Google Workspace credentials exist and the token is valid. When this env var is injected, the task manager SHALL additionally inject `ERRAND_API_URL` and `ERRAND_API_KEY` so the runner can request a mid-task refresh. The startup-time refresh continues to use the standard 5-minute remaining-life buffer; mid-task refreshes use the forced refresh endpoint.

#### Scenario: Google credentials exist and token is fresh
- **WHEN** the task manager prepares a task and Google Workspace credentials exist with a non-expired access token
- **THEN** the container is started with `GOOGLE_WORKSPACE_CLI_TOKEN` set to the access token value
- **AND** the container is started with `ERRAND_API_URL` set to the errand server base URL
- **AND** the container is started with `ERRAND_API_KEY` set to a freshly-generated per-task opaque bearer
- **AND** that bearer is stored in Valkey under `google_refresh_token:<bearer>` with the task ID as the value

#### Scenario: Google credentials exist but token expired
- **WHEN** the task manager prepares a task and Google Workspace credentials exist with an expired (or about-to-expire) token
- **THEN** the task manager refreshes the token before injecting it as `GOOGLE_WORKSPACE_CLI_TOKEN`
- **AND** also injects `ERRAND_API_URL` and `ERRAND_API_KEY`

#### Scenario: No Google credentials
- **WHEN** the task manager prepares a task and no Google Workspace credentials exist
- **THEN** the container is started without the `GOOGLE_WORKSPACE_CLI_TOKEN` environment variable
- **AND** the container does not require `ERRAND_API_URL` or `ERRAND_API_KEY` to be set

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

### Requirement: Mid-task Google access token refresh endpoint

The errand server SHALL expose `POST /api/google/refresh-token`, authenticated by an `Authorization: Bearer <task-scoped-bearer>` header where `<task-scoped-bearer>` is an opaque per-task token generated at task-prepare time and stored in Valkey under `google_refresh_token:<bearer>` → `<task_id>`. The endpoint SHALL NOT accept the global `mcp_api_key` setting as authentication — that key is readable by every task via `/workspace/mcp.json` and would allow a task without Google access to obtain a Google access token. On a successful request, the endpoint SHALL load the stored `google_drive` platform credential, perform a forced OAuth refresh (bypassing the standard 5-minute remaining-life buffer), persist the resulting credential to the database, and return a JSON body of `{ "access_token": "<value>", "expires_at": <epoch_seconds> }`. The endpoint SHALL log the refresh outcome (success or failure) and the new `expires_at` but SHALL NOT log the access token value.

#### Scenario: Authenticated caller receives a fresh token

- **WHEN** a request with a valid `Authorization: Bearer <task-scoped-bearer>` header (i.e. a bearer present in Valkey under `google_refresh_token:<bearer>`) is sent to `POST /api/google/refresh-token` and stored `google_drive` credentials include a working refresh token
- **THEN** the response status is `200`
- **AND** the response body contains a new `access_token` whose value differs from the stored token at request time (or is fresh per Google's response)
- **AND** the new credential is persisted to the `platform_credentials` table

#### Scenario: Unauthenticated caller is rejected

- **WHEN** a request to `POST /api/google/refresh-token` is missing the `Authorization` header, has an empty bearer token, or carries a bearer that has no matching `google_refresh_token:<bearer>` key in Valkey
- **THEN** the response status is `401`
- **AND** no refresh is attempted

#### Scenario: Global mcp_api_key is rejected

- **WHEN** a request to `POST /api/google/refresh-token` carries the `mcp_api_key` setting value as the bearer (i.e. the key used to authenticate the errand MCP server)
- **THEN** the response status is `401`
- **AND** no refresh is attempted

#### Scenario: No Google credentials configured

- **WHEN** a request authorised with the correct bearer token reaches `POST /api/google/refresh-token` but no `google_drive` platform credential exists
- **THEN** the response status is `404`
- **AND** the response body indicates "no Google credentials configured"

#### Scenario: Refresh upstream fails

- **WHEN** the call to Google's token endpoint returns a non-200 response or the persisted refresh token has been revoked
- **THEN** the endpoint returns status `502`
- **AND** the response body contains a short error message identifying the upstream failure
- **AND** the stored credential is left unchanged

#### Scenario: Forced refresh ignores remaining lifetime

- **WHEN** the stored `google_drive` credential's `expires_at` is more than 5 minutes in the future
- **THEN** the endpoint still performs the refresh
- **AND** does not short-circuit on the standard 5-minute buffer used by task-start injection

### Requirement: Task-runner exposes errand API base URL and per-task refresh bearer

The task manager SHALL set environment variables `ERRAND_API_URL` (the errand server base URL, e.g. `http://errand:8000`) and `ERRAND_API_KEY` (a freshly-generated opaque token, e.g. `secrets.token_hex(32)`) on every task-runner container that already receives `GOOGLE_WORKSPACE_CLI_TOKEN`. The base URL SHALL be derivable from `ERRAND_MCP_URL` by stripping the `/mcp/...` suffix. Before injection, the task manager SHALL store the bearer in Valkey under the key `google_refresh_token:<bearer>` with the task ID as the value and a TTL of at least 8 hours. `ERRAND_API_KEY` SHALL NOT be set to the value of the global `mcp_api_key` setting.

#### Scenario: Google credentials present — env vars set

- **WHEN** the task manager prepares a task with Google Workspace credentials and a non-empty `mcp_api_key`
- **THEN** the resulting container environment contains both `ERRAND_API_URL` and `ERRAND_API_KEY` in addition to `GOOGLE_WORKSPACE_CLI_TOKEN`

#### Scenario: No Google credentials — env vars optional

- **WHEN** the task manager prepares a task without Google Workspace credentials
- **THEN** the task-runner does not require `ERRAND_API_URL` or `ERRAND_API_KEY` to be set

### Requirement: Transparent token refresh on `execute_command` auth failure

The task-runner's `execute_command` function tool SHALL inspect the combined stdout and stderr captured from each subprocess. When the captured output contains the literal substring `"status": "UNAUTHENTICATED"` AND `GOOGLE_WORKSPACE_CLI_TOKEN` is set in the runner's environment AND no prior refresh attempt has occurred for this invocation, the wrapper SHALL:

1. Acquire a module-level `asyncio.Lock` (the "refresh lock").
2. Re-read `GOOGLE_WORKSPACE_CLI_TOKEN`; if it differs from the value present when the lock was requested, skip the refresh call (another caller refreshed concurrently).
3. Otherwise, issue `POST ${ERRAND_API_URL}/api/google/refresh-token` with `Authorization: Bearer ${ERRAND_API_KEY}`.
4. On success, update `os.environ["GOOGLE_WORKSPACE_CLI_TOKEN"]` with the returned value.
5. Release the lock.
6. Re-run the same shell command exactly once.
7. Return the retry's output to the agent loop.

The output of the original (auth-failed) invocation SHALL NOT be returned to the agent loop in the success case.

#### Scenario: gws command fails with auth error and retry succeeds

- **WHEN** the agent calls `execute_command` with a `gws` command and the captured output contains `"status": "UNAUTHENTICATED"`
- **THEN** the wrapper calls `/api/google/refresh-token` and receives a new access token
- **AND** updates `os.environ["GOOGLE_WORKSPACE_CLI_TOKEN"]`
- **AND** re-runs the original command
- **AND** the agent loop receives only the retry's output

#### Scenario: gws command fails with auth error and retry also fails

- **WHEN** the wrapper detects `"status": "UNAUTHENTICATED"` in the original output, refreshes successfully, re-runs the command, and the retry output still contains `"status": "UNAUTHENTICATED"`
- **THEN** the wrapper returns the retry's output to the agent loop unchanged
- **AND** does not attempt a second refresh
- **AND** does not loop

#### Scenario: Refresh endpoint returns an error

- **WHEN** the wrapper detects `"status": "UNAUTHENTICATED"`, but `POST /api/google/refresh-token` returns a non-2xx response (or is unreachable)
- **THEN** the wrapper returns the original (auth-failed) output to the agent loop
- **AND** does not re-run the command
- **AND** does not raise

#### Scenario: Concurrent commands deduplicate the refresh

- **WHEN** two `execute_command` calls run in parallel, each detect `"status": "UNAUTHENTICATED"`, and arrive at the refresh lock close in time
- **THEN** exactly one `POST /api/google/refresh-token` request is sent
- **AND** both wrappers use the same new token value for their retries

#### Scenario: GOOGLE_WORKSPACE_CLI_TOKEN not set — no detection

- **WHEN** `execute_command` runs a command that incidentally emits the substring `"status": "UNAUTHENTICATED"` (e.g. printing a JSON file) but `GOOGLE_WORKSPACE_CLI_TOKEN` is not set in the runner environment
- **THEN** the wrapper does not attempt a refresh
- **AND** returns the original output to the agent loop

#### Scenario: Non-gws command emits the auth-failure signature

- **WHEN** `execute_command` runs an arbitrary command (not gws) whose output happens to contain `"status": "UNAUTHENTICATED"` AND `GOOGLE_WORKSPACE_CLI_TOKEN` is set
- **THEN** the wrapper attempts the refresh and one retry
- **AND** if the retry output equals the original, the wrapper returns the retry output (no loop, no error)

### Requirement: Token refresh event emitted in task transcript

The task-runner SHALL emit a `token_refreshed` event to its event stream whenever a mid-task refresh is performed. The event SHALL include a status field (`"ok"` or `"failed"`) and SHALL NOT include the access token value. The event SHALL NOT be added to the LLM conversation history.

#### Scenario: Successful refresh emits ok event

- **WHEN** the wrapper performs a refresh that returns 200
- **THEN** an event `{ "type": "token_refreshed", "data": { "provider": "google_workspace", "status": "ok" } }` is emitted

#### Scenario: Failed refresh emits failed event

- **WHEN** the wrapper attempts a refresh that returns a non-2xx response or raises
- **THEN** an event `{ "type": "token_refreshed", "data": { "provider": "google_workspace", "status": "failed" } }` is emitted
- **AND** the event payload does not include the access token
