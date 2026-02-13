## 1. Add "Retry" tag in `_schedule_retry`

- [x] 1.1 In `_schedule_retry` in `worker.py`, after the UPDATE statement and before the commit, find-or-create a "Retry" tag (same pattern as "Input Needed") and insert into `task_tags` if not already associated
- [x] 1.2 Guard against duplicate association: check if the task already has the "Retry" tag before inserting

## 2. Remove "Retry" tag on success

- [x] 2.1 In the success path (exit_code == 0, parsed successfully), before committing, delete any "Retry" tag association from `task_tags` for the current task
- [x] 2.2 Ensure this works for both `completed` and `review` (needs_input) outcomes

## 3. Tests

- [x] 3.1 Add test: `_schedule_retry` adds "Retry" tag to the task
- [x] 3.2 Add test: second retry does not create duplicate tag association
- [x] 3.3 Add test: successful completion removes "Retry" tag
- [x] 3.4 Add test: task moving to review removes "Retry" tag

## 4. Version bump and verification

- [x] 4.1 Bump VERSION file (patch increment to 0.17.1)
- [x] 4.2 Run full backend test suite and verify all tests pass
