## MODIFIED Requirements

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
