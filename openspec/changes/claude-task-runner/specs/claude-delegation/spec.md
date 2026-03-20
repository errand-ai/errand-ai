## ADDED Requirements

### Requirement: Claude-first execution with fallback
When the `claude` CLI is detected on PATH and `CLAUDE_CODE_OAUTH_TOKEN` is set in the environment, `main.py` SHALL attempt to execute the task via `claude -p` before falling back to the standard Python agent loop. If `claude -p` exits with a non-zero status code, `main.py` SHALL emit a `claude_fallback` event to stderr and execute the task using the standard agent loop.

#### Scenario: Claude succeeds
- **WHEN** the claude-task-runner starts with `claude` on PATH and a valid `CLAUDE_CODE_OAUTH_TOKEN`
- **THEN** the task is executed via `claude -p` and the result is written to stdout in TaskRunnerOutput format

#### Scenario: Claude auth failure triggers fallback
- **WHEN** `claude -p` exits with a non-zero status due to authentication error
- **THEN** a `claude_fallback` event is emitted to stderr with the reason, and the task is re-executed using the standard Python agent loop

#### Scenario: Claude rate limit triggers fallback
- **WHEN** `claude -p` exits with a non-zero status due to rate limiting
- **THEN** a `claude_fallback` event is emitted and the standard agent loop is used

#### Scenario: Claude not on PATH
- **WHEN** the container starts without `claude` on PATH (e.g., default task-runner image)
- **THEN** the standard Python agent loop is used directly (no claude attempt)

#### Scenario: CLAUDE_CODE_OAUTH_TOKEN not set
- **WHEN** the container starts with `claude` on PATH but no `CLAUDE_CODE_OAUTH_TOKEN`
- **THEN** the standard Python agent loop is used directly (no claude attempt)

### Requirement: Claude invocation with streaming output
The `claude -p` invocation SHALL use `subprocess.Popen` with `--output-format stream-json`, `--verbose`, and `--allowedTools` set to `Bash,Read,Edit,Write,Grep,Glob`. The system prompt SHALL be passed via `--append-system-prompt`. The working directory SHALL be set to `/workspace`.

#### Scenario: Claude invocation command
- **WHEN** main.py invokes claude for a task with prompt "Fix the auth bug"
- **THEN** the subprocess command is `claude -p "Fix the auth bug" --output-format stream-json --verbose --allowedTools "Bash,Read,Edit,Write,Grep,Glob" --append-system-prompt "<system prompt>"`

#### Scenario: Working directory
- **WHEN** claude is invoked
- **THEN** the subprocess `cwd` is set to `/workspace`

### Requirement: Stream event transformation
The task-runner SHALL read claude's stdout line by line (NDJSON from `stream-json` format) and transform each event into errand's existing event format, emitting the transformed events to stderr. Unrecognised event types SHALL be emitted as `raw` events to preserve data.

#### Scenario: Tool use start mapped to tool_call
- **WHEN** claude emits a `content_block_start` event with `content_block.type == "tool_use"`
- **THEN** the task-runner emits `{"type": "tool_call", "data": {"tool": "<name>", "args": {...}}}` to stderr

#### Scenario: Tool result mapped
- **WHEN** claude emits tool result content after a tool use block
- **THEN** the task-runner emits `{"type": "tool_result", "data": {"tool": "<name>", "output": "<truncated>"}}` to stderr

#### Scenario: Text delta mapped to thinking
- **WHEN** claude emits a `text_delta` event
- **THEN** the task-runner emits `{"type": "thinking", "data": {"text": "<delta>"}}` to stderr

#### Scenario: Final result mapped to agent_end
- **WHEN** claude emits a `result` event with the final output
- **THEN** the task-runner emits `{"type": "agent_end", "data": {"output": {...}}}` to stderr

#### Scenario: API retry mapped to raw
- **WHEN** claude emits a `system/api_retry` event
- **THEN** the task-runner emits `{"type": "raw", "data": {"line": "<original event>"}}` to stderr

#### Scenario: Unknown event mapped to raw
- **WHEN** claude emits an event type not in the known mapping
- **THEN** the task-runner emits `{"type": "raw", "data": {"line": "<original event>"}}` to stderr

### Requirement: Claude result parsing
When `claude -p` exits with code 0, the task-runner SHALL extract the final result from the last `result` event in the stream and format it as a TaskRunnerOutput JSON object (`{"status": "completed", "result": "..."}`) written to stdout.

#### Scenario: Successful result extraction
- **WHEN** claude exits with code 0 and the stream contained a `result` event with `result: "The bug was fixed"`
- **THEN** stdout contains `{"status": "completed", "result": "The bug was fixed"}`

#### Scenario: No result event despite exit code 0
- **WHEN** claude exits with code 0 but no `result` event was found in the stream
- **THEN** the task-runner falls back to the standard agent loop
