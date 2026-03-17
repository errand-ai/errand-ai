## 1. JSON Repair and Tool Call Sanitization

- [x] 1.1 Implement `_repair_truncated_json(s: str) -> str | None` function in `task-runner/main.py`: track quote parity for unclosed strings, maintain a stack of open delimiters (`{`, `[`), append closing delimiters in reverse order, validate with `json.loads()`, return repaired string or `None`
- [x] 1.2 Implement `_sanitize_tool_calls(messages: list) -> list` function in `task-runner/main.py`: scan assistant messages for `tool_calls` with invalid JSON arguments, attempt repair via `_repair_truncated_json`, replace with `{"error": "malformed_arguments", "original_fragment": "..."}` placeholder if repair fails, log each sanitization at WARNING level
- [x] 1.3 Update `filter_model_input` to call `_sanitize_tool_calls` as the first step before screenshot stripping and context trimming

## 2. Error Classification and Retry Logic

- [x] 2.1 Implement `_classify_error(exc: Exception) -> str` function in `task-runner/main.py`: return `"transient"` for `APIConnectionError`, `APITimeoutError`, `RateLimitError`, HTTP 429/502/503/504; return `"non_retryable"` for `BadRequestError`, `AuthenticationError`, HTTP 500 with tool-conversion messages; return `"unknown"` for everything else
- [x] 2.2 Replace the catch-all `except Exception: sys.exit(1)` block with retry logic: wrap the `Runner.run_streamed()` call and streaming iteration in a retry loop with max 3 attempts and exponential backoff (2s, 4s, 8s) for transient errors; exit immediately for non-retryable and unknown errors
- [x] 2.3 Update `emit_event("error", ...)` calls to include `error_type` and `error_class` fields in the error event data

## 3. Tests

- [x] 3.1 Add tests for `_repair_truncated_json`: missing closing brace, missing closing quote + brace, nested structures, irreparable input returns None, already-valid JSON returns unchanged
- [x] 3.2 Add tests for `_sanitize_tool_calls`: malformed tool call repaired in-place, unrepairable tool call replaced with placeholder, valid tool calls pass through unchanged, non-assistant messages unaffected
- [x] 3.3 Add tests for `_classify_error`: verify classification of `RateLimitError`, `APITimeoutError`, `APIConnectionError`, `BadRequestError`, `AuthenticationError`, HTTP 500 with tool-conversion message, generic `Exception`
- [x] 3.4 Add test for updated `filter_model_input` chain: verify sanitization runs before screenshot stripping and context trimming
- [x] 3.5 Run full test suite (`DATABASE_URL="sqlite+aiosqlite:///:memory:" errand/.venv/bin/python -m pytest errand/tests/ -v` and task-runner tests) to verify no regressions
