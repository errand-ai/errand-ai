## 1. Empty response detection and failure reporting

- [x] 1.1 Add empty output validation after `result.final_output` extraction in `main.py` (after line 727). Check `not str(final_output).strip() if final_output else True`. When empty: emit error event with `error_type: "empty_response"` and `error_class: "EmptyResponseError"`, log the failure, report failed status via `post_result_callback()` and `write_output_file()` with payload `{"status": "failed", "result": "", "error": "LLM returned empty response", "questions": []}`, then `sys.exit(1)`.
- [x] 1.2 Ensure the empty response check runs before `extract_json()` and the fallback output formatting, so that an empty string never reaches the "completed" path.

## 2. Tests

- [x] 2.1 Add test: agent returns empty string final_output — verify error event emitted to stderr with `error_type: "empty_response"`, failed status in callback/output, and exit code 1.
- [x] 2.2 Add test: agent returns None final_output — verify same failure behavior as empty string.
- [x] 2.3 Add test: agent returns whitespace-only final_output (e.g. `"  \n "`) — verify same failure behavior.
- [x] 2.4 Add test: agent returns non-empty final_output (e.g. `"Here is the result"`) — verify output is processed normally and exits with code 0 (regression guard).
