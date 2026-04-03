## ADDED Requirements

### Requirement: ExternalStatusUpdater background service

The system SHALL provide an `ExternalStatusUpdater` class that subscribes to the Valkey `task_events` pub/sub channel and dispatches source-specific callbacks when tasks with external references change status. The updater SHALL be started as an asyncio background task during app lifespan, following the same pattern as `SlackStatusUpdater`. The updater SHALL handle errors gracefully: log the error and continue processing subsequent events (never crash the background task).

#### Scenario: Updater subscribes on startup

- **WHEN** the FastAPI application starts and the ExternalStatusUpdater is initialized
- **THEN** the updater subscribes to the Valkey `task_events` channel and begins listening for messages

#### Scenario: Updater ignores events without external refs

- **WHEN** a `task_updated` event is received for a task that has no ExternalTaskRef
- **THEN** the updater takes no action and continues listening

#### Scenario: Updater skips callback when trigger is deleted

- **WHEN** a `task_updated` event is received for a task with an ExternalTaskRef whose trigger_id is null (trigger was deleted)
- **THEN** the updater logs a debug message and skips the callback

#### Scenario: Updater recovers from callback errors

- **WHEN** a source-specific callback raises an exception (e.g. network error reaching Jira API)
- **THEN** the updater logs the error with task_id and source context, and continues processing the next event

### Requirement: Status transition handling for pending to running

When a task transitions from `pending` to `running` and has an ExternalTaskRef with an active trigger, the updater SHALL dispatch the following actions based on the trigger's `actions` configuration: if `add_comment` is true, post a comment to the external item with the text `"Task started by Errand (task ID: {task_id})"`. If `assign_to` is configured, assign the external item to the specified user.

#### Scenario: Comment posted on task start

- **WHEN** a task transitions to running, has an ExternalTaskRef with source="jira", and the trigger has actions `{"add_comment": true}`
- **THEN** the updater posts a comment "Task started by Errand (task ID: {task_id})" to the Jira issue

#### Scenario: Item assigned on task start

- **WHEN** a task transitions to running, has an ExternalTaskRef with source="jira", and the trigger has actions `{"assign_to": "jsmith"}`
- **THEN** the updater assigns the Jira issue to user "jsmith"

#### Scenario: No action when add_comment is false and assign_to is absent

- **WHEN** a task transitions to running and the trigger has actions `{"add_comment": false}`
- **THEN** the updater takes no action for the pending-to-running transition

### Requirement: Status transition handling for running to completed

When a task transitions from `running` to `completed` and has an ExternalTaskRef with an active trigger, the updater SHALL dispatch the following actions: if `comment_output` is true (or if `add_comment` is true), post a comment containing the task output (truncated to the source's comment character limit). If `transition_on_complete` is configured, transition the external item to the specified status.

#### Scenario: Completion comment with task output

- **WHEN** a task transitions to completed with output "Report generated successfully.\n\n## Findings\n...", has an ExternalTaskRef with source="jira", and the trigger has actions `{"add_comment": true, "comment_output": true}`
- **THEN** the updater posts a comment to the Jira issue containing the task output, truncated to Jira's comment character limit if necessary

#### Scenario: Status transition on completion

- **WHEN** a task transitions to completed, has an ExternalTaskRef with source="jira", and the trigger has actions `{"transition_on_complete": "Done"}`
- **THEN** the updater transitions the Jira issue to the "Done" status

#### Scenario: Both comment and transition on completion

- **WHEN** a task transitions to completed and the trigger has actions `{"add_comment": true, "comment_output": true, "transition_on_complete": "Done"}`
- **THEN** the updater posts the completion comment AND transitions the issue status

### Requirement: Status transition handling for running to failed

When a task transitions from `running` to `failed` and has an ExternalTaskRef with an active trigger, the updater SHALL post a comment with an error summary if `add_comment` is true in the trigger's actions. The comment SHALL include the text `"Task failed in Errand (task ID: {task_id})"` followed by the error message if available. The updater SHALL NOT attempt a status transition on failure.

#### Scenario: Error comment posted on task failure

- **WHEN** a task transitions to failed with error "Container exited with code 1", has an ExternalTaskRef with source="jira", and the trigger has actions `{"add_comment": true}`
- **THEN** the updater posts a comment "Task failed in Errand (task ID: {task_id})\n\nContainer exited with code 1" to the Jira issue

#### Scenario: No comment on failure when add_comment is false

- **WHEN** a task transitions to failed and the trigger has actions `{"add_comment": false}`
- **THEN** the updater takes no action for the failure event

### Requirement: Source-specific callback dispatch

The updater SHALL use a pluggable dispatch mechanism to route callbacks to source-specific handlers. Each source handler (e.g. Jira, GitHub) SHALL implement a common interface for: posting comments, assigning items, adding labels, and transitioning statuses. The dispatcher SHALL select the handler based on the `source` field of the ExternalTaskRef. If no handler is registered for a source, the updater SHALL log a warning and skip the callback.

#### Scenario: Dispatch to Jira handler

- **WHEN** an ExternalTaskRef has source="jira" and a callback is triggered
- **THEN** the updater dispatches to the Jira-specific handler

#### Scenario: Unknown source logged and skipped

- **WHEN** an ExternalTaskRef has source="bitbucket" and no handler is registered for "bitbucket"
- **THEN** the updater logs a warning "No callback handler registered for source: bitbucket" and skips the callback
