## Purpose

ReAct agent execution using OpenAI Agents SDK with streaming events, lazy MCP tool loading, and structured output delivery.

## Requirements

### Requirement: Task runner Python application
The task runner SHALL include a Python application (`main.py`) that serves as the container entrypoint. The application SHALL read the following environment variables: `OPENAI_BASE_URL`, `OPENAI_API_KEY`, `OPENAI_MODEL`, `USER_PROMPT_PATH`, `SYSTEM_PROMPT_PATH`, and `MCP_CONFIGURATION_PATH`. The application SHALL read the contents of the files at `USER_PROMPT_PATH` (user prompt), `SYSTEM_PROMPT_PATH` (system prompt), and `MCP_CONFIGURATION_PATH` (MCP server configuration JSON). The application SHALL exit with code 1 and print an error message to stderr if any required environment variable is missing or any required file cannot be read.

#### Scenario: All inputs available
- **WHEN** the task runner starts with all environment variables set and all files present
- **THEN** the application reads the user prompt, system prompt, and MCP configuration and proceeds to agent execution

#### Scenario: Missing environment variable
- **WHEN** the task runner starts without `OPENAI_API_KEY` set
- **THEN** the application prints an error to stderr and exits with code 1

#### Scenario: Missing prompt file
- **WHEN** the task runner starts with `USER_PROMPT_PATH` pointing to a non-existent file
- **THEN** the application prints an error to stderr and exits with code 1

### Requirement: ReAct agent execution using OpenAI Agents SDK

The task runner application SHALL use the OpenAI Agents SDK to create and run a ReAct agent in streaming mode. The agent SHALL be configured with: (1) the system prompt from `SYSTEM_PROMPT_PATH` with appended output format instructions and the compact tool catalog (see `lazy-mcp-tool-registry` spec), (2) the model specified in `OPENAI_MODEL` passed through as-is, (3) the OpenAI-compatible API base URL from `OPENAI_BASE_URL`, (4) MCP servers with `tool_filter` applied for lazy loading (see `lazy-mcp-tool-registry` spec), (5) `model_settings` with optional reasoning configuration, and (6) native tools including `execute_command`, `discover_tools`, and `submit_result`. The agent SHALL be executed using `Runner.run_streamed()` with a `RunContextWrapper` carrying the `ToolVisibilityContext`, and the application SHALL iterate `result.stream_events()` to process events in real-time.

The `RunConfig` SHALL use `OpenAIProvider` as the `model_provider` instead of the default `MultiProvider`. This bypasses the SDK's slash-based prefix parsing, which would otherwise misinterpret model names containing slashes (e.g. `bedrock/gpt-oss:20b`) as provider prefixes. `OpenAIProvider` passes model names through to the configured OpenAI client unchanged, which is correct since the client already points at the LiteLLM proxy.

#### Scenario: Agent processes prompt with streaming

- **WHEN** the agent receives a user prompt and MCP tools are available
- **THEN** the agent runs in streaming mode, emitting structured events to stderr as it reasons, uses tools, and produces output

#### Scenario: Agent processes prompt without tools

- **WHEN** the agent receives a user prompt and the MCP configuration defines no servers
- **THEN** the agent processes the prompt using only its reasoning capability and native tools (execute_command, submit_result) in streaming mode and produces a structured response

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

### Requirement: Overarching structured output system prompt
The task runner SHALL prepend an overarching system prompt to the user-provided system prompt that instructs the agent to produce its final response as a JSON object with the following schema: `{"status": "completed" | "needs_input", "result": "<string>", "questions": ["<string>"]}`. The `status` field SHALL be `completed` when the agent has fully processed the prompt, or `needs_input` when the agent determines it cannot proceed without user clarification. The `result` field SHALL contain the agent's output text. The `questions` field SHALL contain a list of clarifying questions when `status` is `needs_input`, or an empty list when `status` is `completed`.

#### Scenario: Completed task output
- **WHEN** the agent successfully processes a prompt to completion
- **THEN** the agent outputs JSON with `status: "completed"`, `result` containing the response, and `questions` as an empty list

#### Scenario: Needs input output
- **WHEN** the agent determines it needs clarification from the user
- **THEN** the agent outputs JSON with `status: "needs_input"`, `result` explaining what is unclear, and `questions` containing specific clarifying questions

### Requirement: Task runner outputs structured JSON to stdout
The task runner application SHALL output the agent's structured response as a single JSON line to stdout. Additionally, the task runner SHALL write the same structured JSON to `/output/result.json` if the `/output` directory exists. If the `/output` directory does not exist, the file write SHALL be skipped (backward compatibility with runtimes that don't mount an output volume). The stdout output and file content SHALL be identical. All structured events (agent reasoning, tool calls, errors) SHALL continue to be written to stderr. The application SHALL exit with code 0 on successful completion and exit with code 1 on unrecoverable errors.

#### Scenario: Successful execution output to stdout and file
- **WHEN** the agent completes processing and `/output` directory exists
- **THEN** stdout contains exactly one line of valid JSON matching the `TaskRunnerOutput` schema, `/output/result.json` contains the same JSON, and the exit code is 0

#### Scenario: Successful execution without output directory
- **WHEN** the agent completes processing and `/output` directory does not exist
- **THEN** stdout contains the JSON output, no file is written, and the exit code is 0

#### Scenario: Agent error output
- **WHEN** the agent encounters an unrecoverable error
- **THEN** stderr contains an `error` event with the failure details, stdout is empty, no result.json is written, and the exit code is 1

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

### Requirement: Prompt-based structured output instructions

The task runner SHALL append output format instructions (`OUTPUT_INSTRUCTIONS`) to the user-provided system prompt, instructing the agent to respond with a JSON object matching the `TaskRunnerOutput` schema (`status`, `result`, `questions` fields). SDK-native `output_type` was evaluated but does not work reliably through the LiteLLM proxy for all models, so prompt-based enforcement is used instead.

#### Scenario: System prompt includes output format instructions

- **WHEN** the agent is created with a user-provided system prompt
- **THEN** the agent's instructions contain the user-provided system prompt followed by `OUTPUT_INSTRUCTIONS` describing the expected JSON format

#### Scenario: Agent output matches TaskRunnerOutput schema

- **WHEN** the agent produces its final output
- **THEN** the output is a JSON string matching the `TaskRunnerOutput` schema with `status`, `result`, and `questions` fields

### Requirement: Model settings with optional reasoning

The task runner SHALL configure the agent with `ModelSettings` that includes `reasoning=Reasoning(effort="medium", generate_summary="auto")`. If the model or LLM provider does not support reasoning parameters, the SDK or proxy SHALL silently ignore them without causing an error. The reasoning effort level SHALL be configurable via an optional `REASONING_EFFORT` environment variable (values: `low`, `medium`, `high`; default: `medium`).

#### Scenario: Reasoning enabled for supported model

- **WHEN** the task runner creates the agent and the model supports reasoning (e.g., via LiteLLM's reasoning_effort translation)
- **THEN** the agent's `model_settings` includes `reasoning` with the configured effort level and the model may produce `ReasoningItem` objects in the stream

#### Scenario: Reasoning gracefully ignored for unsupported model

- **WHEN** the task runner creates the agent and the model does not support reasoning parameters
- **THEN** the agent runs normally without errors, and no `ReasoningItem` objects appear in the stream

#### Scenario: Custom reasoning effort via environment variable

- **WHEN** the `REASONING_EFFORT` environment variable is set to `high`
- **THEN** the agent's `model_settings` uses `Reasoning(effort="high", generate_summary="auto")`

#### Scenario: Default reasoning effort

- **WHEN** the `REASONING_EFFORT` environment variable is not set
- **THEN** the agent's `model_settings` uses `Reasoning(effort="medium", generate_summary="auto")`

### Requirement: Task runner pushes result via callback before exiting

The task runner SHALL, after generating structured output and printing it to stdout, attempt to POST the output JSON to a callback URL if configured. The task runner SHALL read `RESULT_CALLBACK_URL` and `RESULT_CALLBACK_TOKEN` from environment variables. If both are set, the task runner SHALL send an HTTP POST to `RESULT_CALLBACK_URL` with the output JSON as the request body, `Content-Type: application/json`, and `Authorization: Bearer <RESULT_CALLBACK_TOKEN>` headers, using a 10-second timeout. If the POST succeeds (HTTP 200), the task runner SHALL log success. If the POST fails (network error, non-200 status, timeout), the task runner SHALL log a warning and continue. If either environment variable is missing, the task runner SHALL skip the callback silently and continue — stdout output and `/output/result.json` file output SHALL still be written as fallbacks. The callback POST SHALL never cause the task runner to exit with an error code.

#### Scenario: Callback POST succeeds

- **WHEN** the task runner completes with structured output and `RESULT_CALLBACK_URL` and `RESULT_CALLBACK_TOKEN` are set, and the backend responds with HTTP 200
- **THEN** the task runner logs success, writes output to stdout, writes to `/output/result.json`, and exits with code 0

#### Scenario: Callback POST fails gracefully

- **WHEN** the task runner completes with structured output and the callback POST returns a non-200 status or times out
- **THEN** the task runner logs a warning, still writes output to stdout and `/output/result.json`, and exits with code 0

#### Scenario: Callback not configured

- **WHEN** the task runner completes with structured output and `RESULT_CALLBACK_URL` is not set
- **THEN** the task runner skips the callback POST silently and continues with stdout and file output as before

#### Scenario: Callback POST network error

- **WHEN** the task runner attempts to POST the result and the backend is unreachable (connection refused, DNS failure)
- **THEN** the task runner logs a warning and exits with code 0 (output still written to stdout and file)

### Requirement: Empty final output validation

After the agent loop completes without exception, the task-runner SHALL check for output in priority order: (1) `submit_result` tool call data from the run context, (2) parseable JSON from `result.final_output`, (3) non-empty raw text from `result.final_output`. If none of these yield a result, and the agent called tools during the run, the task-runner SHALL attempt one empty-response nudge (see `submit-result-tool` spec). If the nudge also fails, or if no tools were called, the task-runner SHALL emit a structured error event, report a failed status via the result callback and output file, and exit with code 1.

#### Scenario: Agent submits result via submit_result tool

- **WHEN** the agent loop completes and `submit_result` was called during the run
- **THEN** the task-runner uses the submitted result directly, regardless of `final_output` content, and exits with code 0

#### Scenario: Agent produces non-empty text output without submit_result

- **WHEN** the agent loop completes, `submit_result` was not called, and `result.final_output` is `"Here is the result..."`
- **THEN** the task-runner processes the text output using the existing JSON extraction / raw text fallback and exits with code 0

#### Scenario: Agent produces empty output after calling tools

- **WHEN** the agent loop completes, `submit_result` was not called, `result.final_output` is empty, and the agent called at least one tool during the run
- **THEN** the task-runner injects a nudge message and re-runs the agent for one additional attempt

#### Scenario: Agent produces empty output with no tool calls

- **WHEN** the agent loop completes, `submit_result` was not called, `result.final_output` is empty, and the agent called zero tools
- **THEN** the task-runner emits an error event with `"error_type": "empty_response"`, reports a failed status, and exits with code 1

#### Scenario: Failed status reported via callback and output file

- **WHEN** empty output is detected after nudge exhaustion and `RESULT_CALLBACK_URL` is configured
- **THEN** the result callback receives `{"status": "failed", "result": "", "error": "LLM returned empty response"}` and the output file contains the same payload

### Requirement: Agent discovers capabilities via skills
The task-runner agent SHALL discover integration-specific instructions by reading SKILL.md files from `/workspace/skills/` rather than receiving them inline in the system prompt. The agent SHALL read the skill manifest in the system prompt to identify relevant skills, then read their SKILL.md files before using the associated tools or capabilities.

#### Scenario: Agent reads cloud storage skill before using cloud tools
- **WHEN** the agent needs to interact with cloud storage (OneDrive)
- **AND** the skills manifest lists a `cloud-storage` skill
- **THEN** the agent reads `/workspace/skills/cloud-storage/SKILL.md` before making cloud storage tool calls

#### Scenario: Agent initiates Hindsight recall
- **WHEN** a task starts and the skills manifest lists a `hindsight-memory` skill
- **THEN** the agent reads the skill and uses Hindsight MCP tools to recall relevant context
- **AND** the agent retains important learnings before completing the task

#### Scenario: Agent discovers repo context conventions
- **WHEN** the agent clones a repository and the skills manifest lists a `repo-context` skill
- **THEN** the agent reads the skill and follows the instructions to discover CLAUDE.md, commands, and repo-level skills

#### Scenario: Agent works without skills
- **WHEN** no skills are available (manifest absent)
- **THEN** the agent proceeds using MCP tool schemas and its base instructions without reading any skill files
