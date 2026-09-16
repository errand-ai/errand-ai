## ADDED Requirements

### Requirement: Task Management tab exposes all task-runtime settings

The Task Management tab (`/settings/tasks`) SHALL let an admin view and edit, through the `@errand-ai/ui-components` cards it renders, every task-runtime setting the server consumes:

- in `<LlmModelCard>`: provider, model and timeout for each model role, and the compaction output-token budget
- in `<TaskManagementCard>`: `archive_after_days`, `max_concurrent_tasks`, `timezone`, `task_runner_log_level`, `max_turns` and `reasoning_effort`

Every input and select in those cards SHALL carry a visible text label that stays visible when the control holds a value; a placeholder alone SHALL NOT serve as the label. A setting the server reports as `readonly` (environment-sourced) SHALL be displayed but not editable, with the card's deployment-locked note. The frontend SHALL pin an `@errand-ai/ui-components` version that provides this behaviour.

#### Scenario: Timeout fields are labelled when populated
- **WHEN** an admin opens `/settings/tasks` and the task processing timeout is `600`
- **THEN** the timeout input shows `600` and a visible label identifying it as the timeout in seconds

#### Scenario: Restored and new fields editable
- **WHEN** an admin opens `/settings/tasks` on a server where none of the four keys is environment-sourced
- **THEN** timezone, task runner log level, max turns and reasoning effort are shown with their current values and can be changed and saved

#### Scenario: Environment-sourced max turns is locked
- **WHEN** the server has `MAX_TURNS` set
- **THEN** the max turns field shows the environment value, is disabled and shows the deployment-locked note

#### Scenario: Profile modal reflects the edited default
- **WHEN** an admin saves `max_turns` as `75` on the Task Management tab and then opens the task profile edit modal
- **THEN** the max turns override placeholder reads "Deployment default: 75"
