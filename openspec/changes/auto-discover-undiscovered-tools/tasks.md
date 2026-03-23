## 1. Core Implementation

- [x] 1.1 Modify `create_tool_filter()` in `task-runner/tool_registry.py` to check `all_known_tools` when a tool is not in `enabled_tools`, auto-add it, log a warning, and return `True`

## 2. Tests

- [x] 2.1 Update `test_tool_filter_blocks_non_enabled` in `task-runner/test_tool_registry.py` to verify that truly unknown tools (not in `all_known_tools`) are still blocked
- [x] 2.2 Add test `test_tool_filter_auto_enables_known_undiscovered` verifying that a tool in `all_known_tools` but not `enabled_tools` is auto-added and the filter returns `True`
- [x] 2.3 Add test `test_tool_filter_auto_enable_logs_warning` verifying that a warning is logged when auto-enabling
- [x] 2.4 Add test `test_tool_filter_auto_enabled_no_repeat_warning` verifying that subsequent calls for the same tool do not log additional warnings
