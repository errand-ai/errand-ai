## Why

The task runner's `runner_logs` field currently only captures stderr from the container, which contains HTTP request logs from the OpenAI Agents SDK (e.g., `POST http://litellm/responses "HTTP/1.1 200 OK"`). There is no visibility into which tools the agent called, what arguments it passed, or what results it received. When a task fails or produces unexpected results — such as the agent not using available MCP tools — debugging requires guessing what happened. Tool call logging would provide the observability needed to diagnose agent behaviour issues.

## What Changes

- Add a custom hook/callback to the OpenAI Agents SDK `Runner.run()` call that logs each tool invocation (tool name, arguments, result summary) to stderr
- The worker already captures stderr as `runner_logs`, so no changes are needed to the worker or database — the tool call logs will automatically appear in the existing `runner_logs` field

## Capabilities

### New Capabilities

- `task-runner-tool-call-logging`: Logging of agent tool calls (name, arguments, result summary) to stderr during task runner execution

### Modified Capabilities

_None — the existing `task-runner-agent` spec does not need requirement changes. Tool call logging is additive behaviour within the task runner process._

## Impact

- `task-runner/main.py` — add tool call logging hook to the agent runner
- `task-runner/test_main.py` — add tests for tool call logging
- No database, worker, frontend, or API changes required
