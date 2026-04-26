## 1. execute_command Output Cap

- [x] 1.1 Calculate `MAX_TOOL_OUTPUT_CHARS` from `MAX_CONTEXT_TOKENS * CHARS_PER_TOKEN * 0.25` in `task-runner/main.py`
- [x] 1.2 Add output truncation to `execute_command` — when stdout exceeds the cap, truncate and append a guidance message about using file-path-based tools
- [x] 1.3 Log a warning when truncation occurs, including the original and truncated sizes

## 2. read_file Binary File Guidance

- [x] 2.1 Update the `read_file` UTF-8 decode error handler to return an actionable error message that identifies the file as binary and directs the agent to file-path-based tools

## 3. System Prompt Directive

- [x] 3.1 Add a "Binary Files" section to the system prompt in `errand/task_manager.py` that instructs the agent never to read binary contents into the conversation

## 4. Testing

- [x] 4.1 Add test for execute_command output truncation at the calculated cap
- [x] 4.2 Add test for execute_command output within cap (no truncation)
- [x] 4.3 Add test for read_file binary file error message
- [x] 4.4 Add test verifying system prompt includes the binary file directive
- [x] 4.5 Run full backend test suite to verify no regressions
