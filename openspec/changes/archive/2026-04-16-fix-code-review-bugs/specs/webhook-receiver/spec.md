## ADDED Requirements

### Requirement: Tracked async task dispatch
The webhook receiver SHALL store references to all asyncio tasks it creates via `asyncio.create_task()` in a module-level set. Each task SHALL have a `done_callback` registered that removes the task from the set and logs any exception at `ERROR` level. This ensures tasks are not garbage-collected before completion and that exceptions are surfaced rather than silently lost.

#### Scenario: Task reference kept until completion
- **WHEN** a webhook is dispatched via `asyncio.create_task()`
- **THEN** the task object is added to the module-level task set before the response is returned

#### Scenario: Task removed from set on completion
- **WHEN** a dispatched task completes successfully
- **THEN** the done callback removes it from the set and no error is logged

#### Scenario: Exception in dispatch task is logged
- **WHEN** a dispatched task raises an unhandled exception
- **THEN** the done callback logs the exception at `ERROR` level and removes the task from the set

#### Scenario: Task not garbage-collected mid-execution
- **WHEN** a dispatched task is long-running and no other code holds a reference to it
- **THEN** the task remains alive because the module-level set holds a strong reference
