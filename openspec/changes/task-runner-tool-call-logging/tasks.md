## 1. ToolCallLogger class

- [x] 1.1 Add `ToolCallLogger(RunHooks)` class to `task-runner/main.py` with `on_tool_start` and `on_tool_end` methods that log tool name, args, and truncated result to stderr via the logger
- [x] 1.2 Add `TOOL_RESULT_MAX_LENGTH = 500` constant and truncation helper

## 2. Hook integration

- [x] 2.1 Pass `ToolCallLogger()` instance as `hooks=` parameter to `Runner.run()` in `main()`

## 3. Post-run MCP tool call logging

- [x] 3.1 After `Runner.run()` returns, iterate over `result.new_items` and log any MCP tool calls using the same `TOOL_CALL`/`TOOL_RESULT` format with `mcp:` prefix

## 4. Tests

- [x] 4.1 Add test that `ToolCallLogger.on_tool_start` logs `TOOL_CALL [<name>] args: ...` to stderr
- [x] 4.2 Add test that `ToolCallLogger.on_tool_end` logs `TOOL_RESULT [<name>] (<len> chars): ...` to stderr
- [x] 4.3 Add test that results exceeding 500 chars are truncated with `...`
- [x] 4.4 Add test for post-run MCP tool call logging with `mcp:` prefix
