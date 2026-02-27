## Purpose

Task position field for sort ordering within kanban columns, with scheduled column sorted by execute_at.

## Requirements

### Requirement: Task position field
Each task SHALL have a `position` integer field representing its sort order within its status column. Lower position values appear higher in the column. The default value SHALL be 0.

#### Scenario: New task gets bottom position
- **WHEN** a task is created with status `new`
- **THEN** its `position` is set to one greater than the maximum position among all tasks with status `new`

#### Scenario: First task in a column
- **WHEN** a task is created and no other tasks exist with the same status
- **THEN** its `position` is set to 1

#### Scenario: Task moved to new column gets bottom position
- **WHEN** a task's status changes from `new` to `pending`
- **THEN** its `position` is set to one greater than the maximum position among all tasks with status `pending`

### Requirement: Scheduled column ordered by execute_at
Tasks in the Scheduled column SHALL be displayed ordered by `execute_at` ascending, with the soonest execution time at the top. Tasks with null `execute_at` SHALL appear at the bottom of the Scheduled column.

#### Scenario: Scheduled tasks sorted by execution time
- **WHEN** the Scheduled column contains tasks with execute_at values of "2026-02-10T10:00:00Z", "2026-02-10T14:00:00Z", and "2026-02-10T09:00:00Z"
- **THEN** the tasks are displayed in order: 09:00, 10:00, 14:00 (soonest at top)

#### Scenario: Null execute_at at bottom
- **WHEN** the Scheduled column contains a task with execute_at "2026-02-10T10:00:00Z" and a task with null execute_at
- **THEN** the task with null execute_at appears below the timed task

### Requirement: Non-scheduled columns ordered by position
Tasks in the New, Pending, Running, and Review columns SHALL be displayed ordered by `position` ascending, with ties broken by `created_at` ascending.

#### Scenario: Tasks ordered by position
- **WHEN** the New column contains tasks with positions 1, 2, and 3
- **THEN** the tasks are displayed in order: position 1 at top, position 3 at bottom

#### Scenario: Same position tie-broken by created_at
- **WHEN** two tasks in the New column both have position 0
- **THEN** the task created earlier appears above the task created later

### Requirement: Completed column ordered by updated_at descending
Tasks in the Completed column SHALL be displayed ordered by `updated_at` descending, so the most recently completed task appears at the top.

#### Scenario: Most recently completed task shown first
- **WHEN** the Completed column contains tasks completed at 09:00, 14:00, and 11:00
- **THEN** the tasks are displayed in order: 14:00 at top, 11:00 in middle, 09:00 at bottom

#### Scenario: Newly completed task appears at top
- **WHEN** a task transitions to `completed` status
- **THEN** its `updated_at` is set to the current time and it appears at the top of the Completed column
