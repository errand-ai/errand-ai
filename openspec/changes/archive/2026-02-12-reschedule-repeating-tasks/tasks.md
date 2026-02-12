## 1. Interval Parsing

- [x] 1.1 Add `parse_interval(interval_str: str) -> timedelta | None` function to `worker.py` that parses simple duration strings (`15m`, `1h`, `1d`, `1w`) into `timedelta` objects; returns `None` for unparseable formats (e.g. crontab)
- [x] 1.2 Add unit tests for `parse_interval`: minutes, hours, days, weeks, and unparseable input

## 2. Rescheduling Logic

- [x] 2.1 Add `_reschedule_if_repeating(task: Task)` async function to `worker.py` that: checks `category == 'repeating'`, checks `repeat_until` hasn't passed, parses the interval, creates a cloned Task with copied fields (title, description, category, repeat_interval, repeat_until, tags) and reset fields (status=scheduled, execute_at=now+interval, output=None, runner_logs=None, retry_count=0, new UUID, position=next in scheduled)
- [x] 2.2 Call `_reschedule_if_repeating(task)` in the `run()` function immediately after moving a repeating task to `completed` (inside the `target_status == "completed"` path)
- [x] 2.3 Publish a `task_created` WebSocket event for the newly cloned task (load with tags via `selectinload`, use `_task_to_dict`)

## 3. Tests

- [x] 3.1 Add test: repeating task with `repeat_interval='30m'` and `repeat_until=null` creates a new scheduled task after completion
- [x] 3.2 Add test: repeating task with `repeat_until` in the future creates a new task
- [x] 3.3 Add test: repeating task with expired `repeat_until` does NOT create a new task
- [x] 3.4 Add test: non-repeating (immediate) completed task does NOT create a new task
- [x] 3.5 Add test: cloned task has correct fields (fresh UUID, status=scheduled, output=null, runner_logs=null, retry_count=0, tags copied)
- [x] 3.6 Add test: `task_created` WebSocket event is published for the rescheduled task
- [x] 3.7 Run full backend test suite and fix any regressions
