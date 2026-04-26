## Why

The task-runner agent can blow past the model's context window in a single tool call by reading binary file contents (e.g., base64-encoding a generated PNG image via `execute_command`). A 400KB PNG produces ~178K tokens of base64 — instantly exceeding a 196K context window. Context compaction cannot recover because the LLM summarisation call itself fails (the context is already too large to send). The task crashes with a 400 error and retries produce the same result every time.

This was observed in production with the nano-banana image generation skill: the agent generates an image, then tries to read it (either via `read_file` which fails on binary, or via `base64` command) before uploading to Google Drive.

## What Changes

- Add a dynamic output size cap to `execute_command` based on `MAX_CONTEXT_TOKENS` — truncates tool output that would consume more than 25% of the context budget, with a guidance message directing the agent to use file-path-based tools instead
- Improve the `read_file` binary file error message to guide the agent away from attempting base64 workarounds
- Add a system prompt directive instructing the agent never to read binary file contents into the conversation

## Capabilities

### New Capabilities

(none)

### Modified Capabilities
- `task-runner-file-tools`: `execute_command` gets a dynamic output cap; `read_file` gets an improved binary file error message
- `agent-context-management`: System prompt updated with binary file handling directive

## Impact

- **task-runner/main.py**: Add output truncation to `execute_command` based on `MAX_CONTEXT_TOKENS * 0.25`; update `read_file` error message for binary files
- **errand/task_manager.py**: Add binary file directive to the system prompt template
- **No migration needed**: Task-runner and server-side changes only
- **No frontend changes**: Backend-only fix
