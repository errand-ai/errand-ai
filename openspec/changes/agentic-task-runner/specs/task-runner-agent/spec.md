## ADDED Requirements

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
The task runner application SHALL use the OpenAI Agents SDK to create and run a ReAct agent. The agent SHALL be configured with: (1) the system prompt from `SYSTEM_PROMPT_PATH` combined with an overarching structured output system prompt, (2) the model specified in `OPENAI_MODEL`, (3) the OpenAI-compatible API base URL from `OPENAI_BASE_URL`, and (4) MCP tools loaded from the configuration at `MCP_CONFIGURATION_PATH`. The agent SHALL process the user prompt from `USER_PROMPT_PATH` through the ReAct loop (reason, act via tools, observe, repeat) until it produces a final response.

#### Scenario: Agent processes prompt with tools
- **WHEN** the agent receives a user prompt and MCP tools are available
- **THEN** the agent reasons about the prompt, uses available MCP tools as needed, and produces a structured response

#### Scenario: Agent processes prompt without tools
- **WHEN** the agent receives a user prompt and the MCP configuration defines no servers
- **THEN** the agent processes the prompt using only its reasoning capability and produces a structured response

#### Scenario: Agent handles tool errors gracefully
- **WHEN** an MCP tool call fails during agent execution
- **THEN** the agent observes the error, reasons about alternatives, and continues processing rather than crashing

### Requirement: Overarching structured output system prompt
The task runner SHALL prepend an overarching system prompt to the user-provided system prompt that instructs the agent to produce its final response as a JSON object with the following schema: `{"status": "completed" | "needs_input", "result": "<string>", "questions": ["<string>"]}`. The `status` field SHALL be `completed` when the agent has fully processed the prompt, or `needs_input` when the agent determines it cannot proceed without user clarification. The `result` field SHALL contain the agent's output text. The `questions` field SHALL contain a list of clarifying questions when `status` is `needs_input`, or an empty list when `status` is `completed`.

#### Scenario: Completed task output
- **WHEN** the agent successfully processes a prompt to completion
- **THEN** the agent outputs JSON with `status: "completed"`, `result` containing the response, and `questions` as an empty list

#### Scenario: Needs input output
- **WHEN** the agent determines it needs clarification from the user
- **THEN** the agent outputs JSON with `status: "needs_input"`, `result` explaining what is unclear, and `questions` containing specific clarifying questions

### Requirement: Task runner outputs structured JSON to stdout
The task runner application SHALL print the agent's structured output JSON to stdout as a single line. All other logging (agent reasoning, tool calls, errors) SHALL be written to stderr. The application SHALL exit with code 0 on successful completion (regardless of whether the status is `completed` or `needs_input`) and exit with code 1 on unrecoverable errors.

#### Scenario: Successful execution output
- **WHEN** the agent completes processing
- **THEN** stdout contains exactly one line of valid JSON matching the structured output schema, and the exit code is 0

#### Scenario: Agent error output
- **WHEN** the agent encounters an unrecoverable error (e.g. API authentication failure)
- **THEN** stderr contains error details, stdout is empty or contains an error JSON, and the exit code is 1

### Requirement: MCP server connection from configuration
The task runner SHALL parse the MCP configuration JSON file to discover and connect to HTTP Streaming MCP servers. The configuration format SHALL be `{"mcpServers": {"<name>": {"url": "<endpoint>", "headers": {…}}}}` where each server entry has a required `url` field and an optional `headers` map. The task runner SHALL only support HTTP Streaming transport — STDIO-based MCP servers (entries with `command`/`args` fields) are not supported and SHALL be skipped with a warning. The task runner SHALL pass the loaded MCP tools to the OpenAI Agents SDK agent.

#### Scenario: Connect to HTTP Streaming MCP server
- **WHEN** the MCP configuration includes `{"mcpServers": {"argocd": {"url": "http://localhost:4000/argocd/mcp", "headers": {"x-litellm-api-key": "Bearer sk-1234"}}}}`
- **THEN** the task runner connects to the HTTP Streaming endpoint and makes its tools available to the agent

#### Scenario: Empty MCP configuration
- **WHEN** the MCP configuration JSON is `{}` or `{"mcpServers": {}}`
- **THEN** the task runner creates the agent with no MCP tools

#### Scenario: MCP server unreachable
- **WHEN** the MCP configuration references a server that cannot be reached
- **THEN** the task runner logs a warning to stderr and continues with any available tools

#### Scenario: STDIO server entry skipped
- **WHEN** the MCP configuration contains an entry with `command` and `args` instead of `url`
- **THEN** the task runner logs a warning to stderr that STDIO servers are not supported and skips the entry
