## ADDED Requirements

### Requirement: Shared next-position utility
The system SHALL provide a shared `_next_position(session, parent_id)` helper in `errand/utils.py`. The function SHALL query the database for the maximum `position` value among tasks with the given `parent_id` and return `max_position + 1` (or `1` if no tasks exist). All modules that previously contained a local copy of this logic (`errand/main.py`, `errand/task_manager.py`, `errand/scheduler.py`, `errand/zombie_cleanup.py`) SHALL import and use the shared function instead of maintaining their own copy.

#### Scenario: No existing tasks for parent
- **WHEN** `_next_position(session, parent_id)` is called and no tasks exist with that `parent_id`
- **THEN** the function returns `1`

#### Scenario: Tasks exist for parent
- **WHEN** `_next_position(session, parent_id)` is called and the maximum `position` among existing tasks is `5`
- **THEN** the function returns `6`

#### Scenario: All call sites use shared function
- **WHEN** any of `main.py`, `task_manager.py`, `scheduler.py`, or `zombie_cleanup.py` need to compute a next position
- **THEN** they call `from errand.utils import _next_position` and do not contain a local implementation
