## MODIFIED Requirements

### Requirement: Non-scheduled columns ordered by position
Tasks in the New, Pending, Running, and Review columns SHALL be displayed ordered by `position` ascending, with ties broken by `created_at` ascending.

#### Scenario: Tasks ordered by position
- **WHEN** the New column contains tasks with positions 1, 2, and 3
- **THEN** the tasks are displayed in order: position 1 at top, position 3 at bottom

#### Scenario: Same position tie-broken by created_at
- **WHEN** two tasks in the New column both have position 0
- **THEN** the task created earlier appears above the task created later

## ADDED Requirements

### Requirement: Completed column ordered by updated_at descending
Tasks in the Completed column SHALL be displayed ordered by `updated_at` descending, so the most recently completed task appears at the top.

#### Scenario: Most recently completed task shown first
- **WHEN** the Completed column contains tasks completed at 09:00, 14:00, and 11:00
- **THEN** the tasks are displayed in order: 14:00 at top, 11:00 in middle, 09:00 at bottom

#### Scenario: Newly completed task appears at top
- **WHEN** a task transitions to `completed` status
- **THEN** its `updated_at` is set to the current time and it appears at the top of the Completed column
