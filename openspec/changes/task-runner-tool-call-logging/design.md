## Design

### Approach: RunHooks subclass with on_tool_start/on_tool_end

The OpenAI Agents SDK provides `RunHooks.on_tool_start` / `on_tool_end` callbacks that fire for all `FunctionTool` invocations. MCP tools (via `MCPServerStreamableHttp`) are converted into `FunctionTool` objects by the SDK's `MCPUtil.to_function_tool()`, so the hooks fire for both local and MCP tools through the same path.

A `ToolCallLogger` subclass of `RunHooks` logs all tool calls via `on_tool_start` and `on_tool_end` to stderr in real-time. After the run completes, a summary count of tool calls is logged from `result.new_items`.

All logging goes to stderr via the existing `logger` (Python `logging` module), which the worker already captures as `runner_logs`.

### Log format

```text
TOOL_CALL [execute_command]
TOOL_RESULT [execute_command] (247 chars): Cloning into 'repo'...
TOOL_CALL [create_pull_request]
TOOL_RESULT [create_pull_request] (132 chars): {"url": "https://github.com/..."}
TOOL_SUMMARY total_tool_calls=2
```

The prefix `TOOL_CALL` and `TOOL_RESULT` makes it easy to grep for tool activity in runner_logs. The result is truncated to a configurable max length (default 500 chars) to avoid bloating logs with large outputs.

Note: The `on_tool_start` hook receives the `Tool` object (with `.name`) but not the per-invocation arguments, so only the tool name is logged at call time. The full result is available via `on_tool_end`.

### Implementation location

All changes are in `task-runner/main.py`:

- Add `TOOL_RESULT_MAX_LENGTH` constant and `_truncate()` helper
- Add `ToolCallLogger(RunHooks)` class
- Pass it to `Runner.run(hooks=...)`
- Add post-run tool call count summary

### What won't change

- No database schema changes
- No worker changes (it already captures stderr as runner_logs)
- No frontend changes
- No API changes
