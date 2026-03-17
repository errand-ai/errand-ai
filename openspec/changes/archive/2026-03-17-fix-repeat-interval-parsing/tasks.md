## 1. Normalise human-readable intervals in parse_interval

- [x] 1.1 Add normalisation logic to `parse_interval` in `errand/task_manager.py`: strip, lowercase, map word units (`minutes?`→`m`, `hours?`→`h`, `days?`→`d`, `weeks?`→`w`), handle `number + space + unit`, and map named intervals (`daily`→`1d`, `weekly`→`1w`, `hourly`→`1h`)
- [x] 1.2 Return both the parsed timedelta AND the normalised compact string from `parse_interval` (or add a separate `normalize_interval` function) so callers can store the normalised form

## 2. Validate and normalise in schedule_task

- [x] 2.1 In `schedule_task` in `errand/mcp_server.py`, call `parse_interval` on `repeat_interval` before storing; return error to caller if unparseable
- [x] 2.2 Store the normalised compact form in the database instead of the raw input
- [x] 2.3 Update the `schedule_task` docstring to document accepted `repeat_interval` formats with examples

## 3. Tests

- [x] 3.1 Add test cases for `parse_interval` with human-readable inputs: `"7 days"`, `"1 hour"`, `"30 minutes"`, `"2 weeks"`, `"daily"`, `"weekly"`, `"hourly"`
- [x] 3.2 Add test case for `parse_interval` with case-insensitive input (e.g. `"7 Days"`)
- [x] 3.3 Verify existing compact format tests still pass (`"15m"`, `"1h"`, `"1d"`, `"1w"`)
