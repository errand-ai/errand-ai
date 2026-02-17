## Requirements

### Requirement: Hindsight memory bank configuration

The system SHALL support configuring a Hindsight memory service via two admin settings: `hindsight_url` (the base URL of the Hindsight API, e.g. `http://hindsight-api.hindsight.svc.cluster.local:8888`) and `hindsight_bank_id` (the memory bank identifier, defaulting to `content-manager-tasks`). These settings SHALL be stored in the existing settings table and manageable via the `PUT /api/settings` endpoint.

#### Scenario: Settings stored and retrieved

- **WHEN** an admin sends `PUT /api/settings` with `{"hindsight_url": "http://hindsight-api:8888", "hindsight_bank_id": "my-bank"}`
- **THEN** both settings are stored and returned by `GET /api/settings`

#### Scenario: Default bank ID

- **WHEN** the `hindsight_bank_id` setting does not exist in the database
- **THEN** the worker SHALL use `content-manager-tasks` as the default bank ID

#### Scenario: Hindsight disabled when URL not configured

- **WHEN** the `hindsight_url` setting does not exist and `HINDSIGHT_URL` environment variable is not set
- **THEN** the worker SHALL skip all Hindsight integration (no MCP injection, no pre-loading)

### Requirement: Worker pre-loads memories before task execution

The worker SHALL call the Hindsight REST API to recall memories relevant to the current task before launching the task runner container. The worker SHALL construct a recall query from the task title and description. The recalled content SHALL be injected into the system prompt as a `## Relevant Context from Memory` section, placed after the admin-configured system prompt and before any MCP tool instructions.

#### Scenario: Memories recalled and injected

- **WHEN** the worker processes a task titled "Deploy frontend v2" and Hindsight returns relevant memories
- **THEN** the system prompt includes a `## Relevant Context from Memory` section containing the recalled content

#### Scenario: No relevant memories found

- **WHEN** the worker recalls from Hindsight and no relevant memories exist
- **THEN** the worker proceeds without adding a memory context section to the system prompt

#### Scenario: Hindsight API unreachable during recall

- **WHEN** the worker attempts to recall from Hindsight and the API is unreachable or returns an error
- **THEN** the worker logs a warning and proceeds without memory context (task execution is not blocked)

#### Scenario: Recall token budget

- **WHEN** the worker recalls memories from Hindsight
- **THEN** the recall request SHALL specify `max_tokens: 2048` to limit the injected context size

### Requirement: Worker injects Hindsight MCP server for task runner

The worker SHALL inject a `hindsight` entry into the task runner's MCP server configuration when Hindsight is configured. The MCP server URL SHALL follow the single-bank pattern: `{hindsight_url}/mcp/{bank_id}/`. The injection SHALL follow the same pattern as existing MCP server injections (Perplexity, content-manager backend): inject only if not already present in the database-configured MCP servers.

#### Scenario: Hindsight MCP server injected

- **WHEN** the worker processes a task with `HINDSIGHT_URL` set to `http://hindsight-api:8888` and bank ID `content-manager-tasks`
- **THEN** the MCP configuration includes `{"hindsight": {"url": "http://hindsight-api:8888/mcp/content-manager-tasks/"}}`

#### Scenario: Database MCP config takes precedence

- **WHEN** the database MCP configuration already contains a `hindsight` entry
- **THEN** the worker SHALL NOT overwrite it with the injected entry

#### Scenario: System prompt includes memory instructions

- **WHEN** the worker injects the Hindsight MCP server
- **THEN** the worker SHALL append a memory usage instruction section to the system prompt instructing the agent that it has access to Hindsight memory tools (`retain`, `recall`, `reflect`) and should use them to store important learnings and recall relevant context

### Requirement: Hindsight URL from environment or settings

The worker SHALL resolve the Hindsight URL from the `HINDSIGHT_URL` environment variable first, falling back to the `hindsight_url` admin setting. Similarly, the bank ID SHALL come from `HINDSIGHT_BANK_ID` environment variable first, falling back to the `hindsight_bank_id` admin setting, with a final default of `content-manager-tasks`.

#### Scenario: Environment variable takes precedence

- **WHEN** `HINDSIGHT_URL` is set to `http://hindsight:8888` and the admin setting `hindsight_url` is `http://other:8888`
- **THEN** the worker uses `http://hindsight:8888`

#### Scenario: Falls back to admin setting

- **WHEN** `HINDSIGHT_URL` is not set and the admin setting `hindsight_url` is `http://hindsight-api:8888`
- **THEN** the worker uses `http://hindsight-api:8888`
