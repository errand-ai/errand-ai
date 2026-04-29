## 1. Backend: buffer writes in task manager

- [x] 1.1 Add `task_log_buffer_max_entries` (default 5000) and `task_log_buffer_ttl_seconds` (default 86400) to admin settings (DB-backed) and load alongside `max_concurrent_tasks` in `errand/task_manager.py`
- [x] 1.2 In the log-publish loop in `errand/task_manager.py` (`_run_in_container`, around line 1534–1546), after each successful `valkey.publish(log_channel, msg)` also append to the buffer: `await valkey.rpush(f"task_logs_buffer:{task.id}", msg)`, then `await valkey.ltrim(...)` to the cap and `await valkey.expire(...)` to the TTL — wrap in a try/except that logs a warning and does NOT abort the live publish
- [x] 1.3 After publishing `task_log_end` (around line 1551–1555), `await valkey.delete(f"task_logs_buffer:{task.id}")` (best-effort, log on failure)

## 2. Backend: SSE replay on connect

- [x] 2.1 In `errand/main.py` `sse_task_logs` (~line 2436), after subscribing to the pub/sub channel and before entering the live `while True:` loop, `LRANGE` the `task_logs_buffer:{task_id}` key and emit each entry as `data: <entry>\n\n`, preserving order
- [x] 2.2 Skip the replay step cleanly when the buffer is empty or missing (no error, no extra messages)
- [x] 2.3 Ensure subscribe-before-snapshot ordering: `pubsub.subscribe(...)` MUST happen before `LRANGE`
- [x] 2.4 Detect `task_log_end` inside replayed entries (a buffer can contain the end sentinel if the task ended between subscribe and LRANGE) and short-circuit to the existing end-of-stream handling

## 3. Backend: tests

- [x] 3.1 Unit test in `errand/tests/test_worker.py` covering buffer push + trim + expire on each event publish
- [x] 3.2 Unit test covering buffer deletion on `task_log_end`
- [x] 3.3 Unit test for `sse_task_logs` that seeds a buffer, opens a stream, asserts the replayed events arrive in order before any new pub/sub message
- [x] 3.4 Test that `sse_task_logs` falls through cleanly when the buffer is empty
- [x] 3.5 Test that buffer-write failures are logged and do not abort the live publish

## 4. Frontend: spec alignment

- [x] 4.1 Verify `TaskLogViewer` live mode in `@errand-ai/ui-components` already hides the "Waiting for logs..." placeholder once any event has been received (buffered or live); add a regression test if missing — confirmed: `waiting.value = false` is set on the first `onmessage` regardless of source (TaskLogViewer.vue:168-169)
- [x] 4.2 If the package has its own test suite, add a vitest case that opens the modal in live mode against a mock SSE source that immediately emits a burst of events and asserts the placeholder is gone after the first event renders — N/A: `@errand-ai/ui-components` is an external npm package, not vendored in this repo

## 5. Verification

- [x] 5.1 Local docker-compose: start a long-running task (e.g., one with a slow agent step), open the modal partway through, confirm previously-emitted events appear immediately and live events continue to flow — confirmed manually by user
- [x] 5.2 Confirm the buffer key is removed from Valkey after the task ends (`redis-cli KEYS 'task_logs_buffer:*'` returns nothing for finished tasks) — confirmed manually by user
- [x] 5.3 Confirm `task_log_buffer_max_entries` setting is honoured by emitting more than the cap and verifying only the latest N entries replay — confirmed manually by user (trim/expire also unit-tested in 3.1)

## 6. Documentation and release

- [x] 6.1 Bump `VERSION` per semver (minor — backwards-compatible feature) — bumped 0.115.9 → 0.116.0; further bumped to 0.116.1 (patch) for review-fix redeploy
- [x] 6.2 Note the new admin settings (`task_log_buffer_max_entries`, `task_log_buffer_ttl_seconds`) in the admin settings UI/help text if applicable — exposed via `settings_registry.SETTINGS_REGISTRY` so they appear in the `/api/settings` response with sensible defaults; surfacing them in the Task Management settings UI is left as a follow-up since these are advanced operator tunables that rarely need adjustment
- [x] 6.3 PR description references this change directory and links the modified specs — done in PR #171 body (links to change dir, proposal, design, and both spec deltas)
