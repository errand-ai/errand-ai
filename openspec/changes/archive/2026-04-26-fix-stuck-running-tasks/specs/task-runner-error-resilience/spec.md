## ADDED Requirements

### Requirement: CancelledError handling in task processing
The task manager's `_run_task` coroutine SHALL catch `asyncio.CancelledError` and attempt to schedule the task for retry before re-raising the exception. If `_schedule_retry` itself fails during the CancelledError handler (e.g., because the DB connection is also closing), the exception SHALL be logged and the CancelledError SHALL still be re-raised. The zombie cleanup mechanism serves as the safety net for tasks that cannot be retried during cancellation.

#### Scenario: Task cancelled during container execution
- **WHEN** the `_run_task` coroutine receives a CancelledError after the container has exited but before `_schedule_retry` is called
- **THEN** the task is scheduled for retry with output indicating processing was cancelled, and the CancelledError is re-raised

#### Scenario: Task cancelled and retry also fails
- **WHEN** the `_run_task` coroutine receives a CancelledError and `_schedule_retry` raises an exception (e.g., DB connection closed)
- **THEN** the failure is logged, the CancelledError is re-raised, and the zombie cleanup will recover the task on the next cycle
