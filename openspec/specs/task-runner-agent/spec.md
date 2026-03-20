## MODIFIED Requirements

### Requirement: ReAct agent execution using OpenAI Agents SDK

The task runner application SHALL use the OpenAI Agents SDK to create and run a ReAct agent in streaming mode. The agent SHALL be configured with: (1) the system prompt from `SYSTEM_PROMPT_PATH` with appended output format instructions and the compact tool catalog (see `lazy-mcp-tool-registry` spec), (2) the model specified in `OPENAI_MODEL` passed through as-is, (3) the OpenAI-compatible API base URL from `OPENAI_BASE_URL`, (4) MCP servers with `tool_filter` applied for lazy loading (see `lazy-mcp-tool-registry` spec), (5) `model_settings` with optional reasoning configuration, and (6) native tools including `execute_command` and `discover_tools`. The agent SHALL be executed using `Runner.run_streamed()` with a `RunContextWrapper` carrying the `ToolVisibilityContext`, and the application SHALL iterate `result.stream_events()` to process events in real-time.

The `RunConfig` SHALL use `OpenAIProvider` as the `model_provider` instead of the default `MultiProvider`. This bypasses the SDK's slash-based prefix parsing, which would otherwise misinterpret model names containing slashes (e.g. `bedrock/gpt-oss:20b`) as provider prefixes. `OpenAIProvider` passes model names through to the configured OpenAI client unchanged, which is correct since the client already points at the LiteLLM proxy.

#### Scenario: Agent processes prompt with streaming

- **WHEN** the agent receives a user prompt and MCP tools are available
- **THEN** the agent runs in streaming mode, emitting structured events to stderr as it reasons, uses tools, and produces output

#### Scenario: Agent processes prompt without tools

- **WHEN** the agent receives a user prompt and the MCP configuration defines no servers
- **THEN** the agent processes the prompt using only its reasoning capability and native tools (execute_command) in streaming mode and produces a structured response

#### Scenario: Agent handles tool errors gracefully

- **WHEN** an MCP tool call fails during agent execution
- **THEN** the agent observes the error, reasons about alternatives, and continues processing rather than crashing

#### Scenario: Model name with slash is routed correctly

- **WHEN** `OPENAI_MODEL` is set to `bedrock/gpt-oss:20b`
- **THEN** the model is passed to the Agent SDK as `bedrock/gpt-oss:20b` unchanged, and `OpenAIProvider` forwards it to the configured OpenAI client (LiteLLM) without prefix parsing

#### Scenario: Model name without slash is routed correctly

- **WHEN** `OPENAI_MODEL` is set to `gpt-4o`
- **THEN** the model is passed to the Agent SDK as `gpt-4o` unchanged, routed through `OpenAIProvider` to the configured OpenAI client

#### Scenario: No litellm package dependency required

- **WHEN** the task-runner container does not have the `litellm` Python package installed
- **THEN** model routing still works correctly because `OpenAIProvider` uses the OpenAI SDK client directly, not the `litellm` library

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

### Requirement: Empty final output validation

After the agent loop completes without exception, the task-runner SHALL validate that `result.final_output` is non-empty before reporting success. The output SHALL be considered empty when `final_output` is `None`, an empty string `""`, or a string containing only whitespace characters. When empty output is detected, the task-runner SHALL NOT report the task as completed. Instead, it SHALL emit a structured error event, report a failed status via the result callback and output file, and exit with code 1.

#### Scenario: Agent produces non-empty output

- **WHEN** the agent loop completes and `result.final_output` is `"Here is the result..."`
- **THEN** the task-runner processes the output normally and exits with code 0

#### Scenario: Agent produces empty string output

- **WHEN** the agent loop completes and `result.final_output` is `""`
- **THEN** the task-runner emits an error event with `"error_type": "empty_response"`, reports a failed status, and exits with code 1

#### Scenario: Agent produces None output

- **WHEN** the agent loop completes and `result.final_output` is `None`
- **THEN** the task-runner emits an error event with `"error_type": "empty_response"`, reports a failed status, and exits with code 1

#### Scenario: Agent produces whitespace-only output

- **WHEN** the agent loop completes and `result.final_output` is `"   \n  "`
- **THEN** the task-runner emits an error event with `"error_type": "empty_response"`, reports a failed status, and exits with code 1

#### Scenario: Failed status reported via callback and output file

- **WHEN** empty output is detected and `RESULT_CALLBACK_URL` is configured
- **THEN** the result callback receives `{"status": "failed", "result": "", "error": "LLM returned empty response"}` and the output file contains the same payload
