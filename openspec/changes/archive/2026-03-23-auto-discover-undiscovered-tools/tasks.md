## 1. Core Implementation

- [x] 1.1 Import `ModelBehaviorError` from `agents.exceptions` in `main.py`
- [x] 1.2 Add `except ModelBehaviorError` handler in retry loop that parses tool name, auto-enables in `visibility_ctx`, and retries
- [x] 1.3 Add `agents.exceptions` mock with real `ModelBehaviorError` class in `conftest.py`

## 2. Tests

- [x] 2.1 Add test for regex parsing of tool name from ModelBehaviorError message
- [x] 2.2 Add test verifying known tool is auto-enabled in visibility context
- [x] 2.3 Add test verifying unknown tool is not auto-enabled
- [x] 2.4 Fix stale `on_llm_start`/`on_llm_end` tests (expected debug logs, now emit stderr JSON)
