## MODIFIED Requirements

### Requirement: Auto-routing after task creation

After a task is created and categorised, the backend SHALL automatically set the task's status based on its category and tags. If the task has a "Needs Info" tag, the task SHALL be set to status `review`. Otherwise: `immediate` tasks SHALL be moved to `pending`, and `scheduled` or `repeating` tasks SHALL be moved to `scheduled`.

#### Scenario: Immediate task without Needs Info moves to pending

- **WHEN** a task is created with category `immediate` and no "Needs Info" tag
- **THEN** the task's status is set to `pending`

#### Scenario: Scheduled task without Needs Info moves to scheduled

- **WHEN** a task is created with category `scheduled` and no "Needs Info" tag
- **THEN** the task's status is set to `scheduled`

#### Scenario: Repeating task without Needs Info moves to scheduled

- **WHEN** a task is created with category `repeating` and no "Needs Info" tag
- **THEN** the task's status is set to `scheduled`

#### Scenario: Task with Needs Info goes to review

- **WHEN** a task is created with category `immediate` but has the "Needs Info" tag
- **THEN** the task's status is set to `review`

#### Scenario: Short input goes to review

- **WHEN** a task is created with a short input (5 words or fewer)
- **THEN** the task gets the "Needs Info" tag and is set to status `review`

#### Scenario: LLM failure goes to review

- **WHEN** a task is created with a long input but the LLM call fails
- **THEN** the task gets the "Needs Info" tag and is set to status `review`

## REMOVED Requirements

### Requirement: Auto-promotion from New on edit

**Reason**: The `new` status no longer exists. Tasks that previously landed in "New" now go to "Review". Users can manually drag tasks from Review to other columns after editing them. The auto-promotion convenience is no longer needed.

**Migration**: Users edit the task in the Review column and manually drag it to Scheduled or Pending as appropriate.
