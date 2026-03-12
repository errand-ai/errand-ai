## MODIFIED Requirements

### Requirement: ReAct agent execution using OpenAI Agents SDK

The task runner application SHALL use the OpenAI Agents SDK to create and run a ReAct agent in streaming mode. The agent SHALL be configured with: (1) the system prompt from `SYSTEM_PROMPT_PATH` with appended output format instructions and the compact tool catalog (see `lazy-mcp-tool-registry` spec), (2) the model specified in `OPENAI_MODEL`, (3) the OpenAI-compatible API base URL from `OPENAI_BASE_URL`, (4) MCP servers with `tool_filter` applied for lazy loading (see `lazy-mcp-tool-registry` spec), (5) `model_settings` with optional reasoning configuration, and (6) native tools including `execute_command` and `discover_tools`. The agent SHALL be executed using `Runner.run_streamed()` with a `RunContextWrapper` carrying the `ToolVisibilityContext`, and the application SHALL iterate `result.stream_events()` to process events in real-time.

#### Scenario: Agent processes prompt with streaming

- **WHEN** the agent receives a user prompt and MCP tools are available
- **THEN** the agent runs in streaming mode, emitting structured events to stderr as it reasons, uses tools, and produces output

#### Scenario: Agent processes prompt without tools

- **WHEN** the agent receives a user prompt and the MCP configuration defines no servers
- **THEN** the agent processes the prompt using only its reasoning capability and native tools (execute_command) in streaming mode and produces a structured response

#### Scenario: Agent handles tool errors gracefully

- **WHEN** an MCP tool call fails during agent execution
- **THEN** the agent observes the error, reasons about alternatives, and continues processing rather than crashing

### Requirement: MCP server connection from configuration

The task runner SHALL parse the MCP configuration JSON file to discover and connect to HTTP Streaming MCP servers. The configuration format SHALL be `{"mcpServers": {"<name>": {"url": "<endpoint>", "headers": {…}}}}` where each server entry has a required `url` field and an optional `headers` map. The task runner SHALL only support HTTP Streaming transport -- STDIO-based MCP servers (entries with `command`/`args` fields) are not supported and SHALL be skipped with a warning. Each `MCPServerStreamableHttp` SHALL be constructed with `cache_tools_list=True`. After connecting, the task runner SHALL call `list_tools()` on each server to build the compact tool catalog, then attach the `tool_filter` callable to each server (the SDK requires `run_context` for dynamic filters, so the filter cannot be set at construction time). The task runner SHALL pass the connected MCP servers to the OpenAI Agents SDK agent.

#### Scenario: Connect to HTTP Streaming MCP server with tool filter

- **WHEN** the MCP configuration includes `{"mcpServers": {"argocd": {"url": "http://localhost:4000/argocd/mcp", "headers": {"x-litellm-api-key": "Bearer sk-1234"}}}}`
- **THEN** the task runner connects with `tool_filter` applied, builds the catalog entry for "argocd", and only hot-listed tools from argocd are visible on the first turn

#### Scenario: Connect to Hindsight MCP server

- **WHEN** the MCP configuration includes `{"mcpServers": {"hindsight": {"url": "http://hindsight-api:8888/mcp/errand-tasks/"}}}`
- **THEN** the task runner connects with `tool_filter` applied, and `retain` and `recall` are immediately visible (hot-listed) while other hindsight tools require discovery

#### Scenario: Empty MCP configuration

- **WHEN** the MCP configuration JSON is `{}` or `{"mcpServers": {}}`
- **THEN** the task runner creates the agent with no MCP tools and no catalog in the system prompt

#### Scenario: MCP server unreachable

- **WHEN** the MCP configuration references a server that cannot be reached
- **THEN** the task runner logs a warning to stderr and continues with any available tools

#### Scenario: STDIO server entry skipped

- **WHEN** the MCP configuration contains an entry with `command` and `args` instead of `url`
- **THEN** the task runner logs a warning to stderr that STDIO servers are not supported and skips the entry
