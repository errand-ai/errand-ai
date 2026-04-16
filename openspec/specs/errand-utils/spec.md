## Purpose

Shared utility helpers in `errand/utils.py` used across the backend to eliminate duplicated logic and ensure consistent behaviour.

## Requirements

### Requirement: Shared next-position utility
The system SHALL provide a shared `_next_position(session, status, exclude_id=None)` helper in `errand/utils.py`. The function SHALL query the database for the maximum `position` value among tasks whose `status` column equals the given value, and return `max_position + 1` (or `1` if no tasks match). The optional `exclude_id` argument SHALL exclude a specific task from the max computation (used when recomputing a task's own position during a column move). All modules that previously contained a local copy of this logic (`errand/main.py`, `errand/task_manager.py`, `errand/scheduler.py`, `errand/zombie_cleanup.py`) SHALL import and use the shared function instead of maintaining their own copy.

#### Scenario: No existing tasks in the status column
- **WHEN** `_next_position(session, status)` is called and no tasks exist with that `status`
- **THEN** the function returns `1`

#### Scenario: Tasks exist in the status column
- **WHEN** `_next_position(session, status)` is called and the maximum `position` among existing tasks with that status is `5`
- **THEN** the function returns `6`

#### Scenario: exclude_id omits a specific task from the max
- **WHEN** `_next_position(session, status, exclude_id=<uuid>)` is called and the task with that id would otherwise be the max-position row
- **THEN** the function returns the next position computed with that task excluded from the query

#### Scenario: All call sites use shared function
- **WHEN** any of `main.py`, `task_manager.py`, `scheduler.py`, or `zombie_cleanup.py` need to compute a next position
- **THEN** they call `from utils import _next_position` and do not contain a local implementation
