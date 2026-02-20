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

The task runner application SHALL use the OpenAI Agents SDK to create and run a ReAct agent in streaming mode. The agent SHALL be configured with: (1) the system prompt from `SYSTEM_PROMPT_PATH` with appended output format instructions, (2) the model specified in `OPENAI_MODEL`, (3) the OpenAI-compatible API base URL from `OPENAI_BASE_URL`, (4) MCP tools loaded from the configuration at `MCP_CONFIGURATION_PATH`, and (5) `model_settings` with optional reasoning configuration. The agent SHALL be executed using `Runner.run_streamed()` and the application SHALL iterate `result.stream_events()` to process events in real-time.

#### Scenario: Agent processes prompt with streaming

- **WHEN** the agent receives a user prompt and MCP tools are available
- **THEN** the agent runs in streaming mode, emitting structured events to stderr as it reasons, uses tools, and produces output

#### Scenario: Agent processes prompt without tools

- **WHEN** the agent receives a user prompt and the MCP configuration defines no servers
- **THEN** the agent processes the prompt using only its reasoning capability in streaming mode and produces a structured response

#### Scenario: Agent handles tool errors gracefully

- **WHEN** an MCP tool call fails during agent execution
- **THEN** the agent observes the error, reasons about alternatives, and continues processing rather than crashing

### Requirement: Prompt-based structured output instructions

The task runner SHALL append output format instructions (`OUTPUT_INSTRUCTIONS`) to the user-provided system prompt, instructing the agent to respond with a JSON object matching the `TaskRunnerOutput` schema (`status`, `result`, `questions` fields). SDK-native `output_type` was evaluated but does not work reliably through the LiteLLM proxy for all models, so prompt-based enforcement is used instead.

#### Scenario: System prompt includes output format instructions

- **WHEN** the agent is created with a user-provided system prompt
- **THEN** the agent's instructions contain the user-provided system prompt followed by `OUTPUT_INSTRUCTIONS` describing the expected JSON format

#### Scenario: Agent output matches TaskRunnerOutput schema

- **WHEN** the agent produces its final output
- **THEN** the output is a JSON string matching the `TaskRunnerOutput` schema with `status`, `result`, and `questions` fields

### Requirement: Task runner outputs structured JSON to stdout

The task runner application SHALL output the agent's structured response as a single JSON line to stdout. Additionally, the task runner SHALL write the same structured JSON to `/output/result.json` if the `/output` directory exists. If the `/output` directory does not exist, the file write SHALL be skipped (backward compatibility with runtimes that don't mount an output volume). The stdout output and file content SHALL be identical. The task runner SHALL parse `result.final_output` using a multi-strategy extraction approach: (1) parse the full stripped text as JSON directly, (2) locate a markdown code fence block and extract its contents, (3) find the first `{` and last `}` in the text and extract that substring. The first strategy that produces a valid `TaskRunnerOutput` object SHALL be used. If all strategies fail, the task runner SHALL wrap the raw output as a fallback `TaskRunnerOutput`. The worker SHALL also use `extract_json()` to handle any preamble text or code fences in the stdout. All structured events (agent reasoning, tool calls, errors) SHALL be written to stderr. The application SHALL exit with code 0 on successful completion and exit with code 1 on unrecoverable errors.

#### Scenario: Successful execution output to stdout and file

- **WHEN** the agent completes processing and `/output` directory exists
- **THEN** stdout contains exactly one line of valid JSON matching the `TaskRunnerOutput` schema, `/output/result.json` contains the same JSON, and the exit code is 0

#### Scenario: Successful execution without output directory

- **WHEN** the agent completes processing and `/output` directory does not exist
- **THEN** stdout contains the JSON output, no file is written, and the exit code is 0

#### Scenario: Agent error output

- **WHEN** the agent encounters an unrecoverable error (e.g. API authentication failure)
- **THEN** stderr contains an `error` event with the failure details, stdout is empty, no result.json is written, and the exit code is 1

#### Scenario: Structured output parsing fallback

- **WHEN** the agent's final output cannot be parsed as valid `TaskRunnerOutput` JSON
- **THEN** the task runner wraps the raw output as `{"status": "completed", "result": "<raw>", "questions": []}`, outputs it to stdout, and exits with code 0

#### Scenario: Agent output with preamble text before JSON
- **WHEN** the agent produces output like `Here is the result:\n{"status": "completed", "result": "done", "questions": []}`
- **THEN** the task runner extracts the JSON object from the text, validates it, and outputs the parsed JSON to stdout

#### Scenario: Agent output with code fence
- **WHEN** the agent produces output starting with ```` ```json\n{"status": "completed", "result": "done", "questions": []}\n``` ````
- **THEN** the task runner extracts the JSON from the code fence, validates it, and outputs the parsed JSON to stdout

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

### Requirement: MCP server connection from configuration

The task runner SHALL parse the MCP configuration JSON file to discover and connect to HTTP Streaming MCP servers. The configuration format SHALL be `{"mcpServers": {"<name>": {"url": "<endpoint>", "headers": {…}}}}` where each server entry has a required `url` field and an optional `headers` map. The task runner SHALL only support HTTP Streaming transport -- STDIO-based MCP servers (entries with `command`/`args` fields) are not supported and SHALL be skipped with a warning. The task runner SHALL pass the loaded MCP tools to the OpenAI Agents SDK agent. When a `hindsight` MCP server is configured, the agent SHALL have access to Hindsight memory tools (`retain`, `recall`, `reflect`) alongside any other configured MCP tools.

#### Scenario: Connect to HTTP Streaming MCP server

- **WHEN** the MCP configuration includes `{"mcpServers": {"argocd": {"url": "http://localhost:4000/argocd/mcp", "headers": {"x-litellm-api-key": "Bearer sk-1234"}}}}`
- **THEN** the task runner connects to the HTTP Streaming endpoint and makes its tools available to the agent

#### Scenario: Connect to Hindsight MCP server

- **WHEN** the MCP configuration includes `{"mcpServers": {"hindsight": {"url": "http://hindsight-api:8888/mcp/errand-tasks/"}}}`
- **THEN** the task runner connects to the Hindsight MCP endpoint and makes `retain`, `recall`, and `reflect` tools available to the agent

#### Scenario: Empty MCP configuration

- **WHEN** the MCP configuration JSON is `{}` or `{"mcpServers": {}}`
- **THEN** the task runner creates the agent with no MCP tools

#### Scenario: MCP server unreachable

- **WHEN** the MCP configuration references a server that cannot be reached
- **THEN** the task runner logs a warning to stderr and continues with any available tools

#### Scenario: STDIO server entry skipped

- **WHEN** the MCP configuration contains an entry with `command` and `args` instead of `url`
- **THEN** the task runner logs a warning to stderr that STDIO servers are not supported and skips the entry

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
