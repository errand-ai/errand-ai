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

### Requirement: GitHub column transition on task running

When a task transitions from `pending` to `running` and has an ExternalTaskRef with `source: "github"` and an active trigger, the updater SHALL check the trigger's `actions` for `column_on_running`. If present, the updater SHALL use the GitHub GraphQL client to update the project item's Status field to the specified column. The project item ID, field ID, and option ID SHALL be resolved from the ExternalTaskRef metadata and the trigger's cached `column_options` mapping.

#### Scenario: Move to "In Progress" on task start

- **WHEN** a task transitions to running, has an ExternalTaskRef with source="github", and the trigger has actions `{"column_on_running": "In Progress", "project_field_id": "PVTSSF_...", "column_options": {"In Progress": "opt_123"}}`
- **THEN** the updater calls the GitHub GraphQL API to update the project item's Status to "In Progress"

#### Scenario: Column transition not configured

- **WHEN** a task transitions to running and the trigger's actions do not contain `column_on_running`
- **THEN** the updater does not perform a column transition

#### Scenario: Column transition fails

- **WHEN** the GraphQL mutation to update the column fails (e.g., stale option ID)
- **THEN** the updater logs the error and continues processing other actions (does not crash)

### Requirement: GitHub comment on task running

When a task transitions from `pending` to `running` and has an ExternalTaskRef with `source: "github"` and the trigger has `actions.add_comment: true`, the updater SHALL post a comment on the GitHub issue using the GraphQL `addComment` mutation. The comment SHALL include the text `"Errand task started (task ID: {task_id})"`. The issue node ID SHALL be obtained from the ExternalTaskRef metadata (`content_node_id`).

#### Scenario: Comment posted on task start

- **WHEN** a task transitions to running, has an ExternalTaskRef with source="github", and the trigger has actions `{"add_comment": true}`
- **THEN** the updater posts a comment "Errand task started (task ID: {task_id})" on the GitHub issue

### Requirement: GitHub actions on task completion

When a task transitions from `running` to `completed` and has an ExternalTaskRef with `source: "github"` and an active trigger, the updater SHALL perform the following actions in order:

1. **Parse structured output**: Extract the fenced JSON block from the task output. If no valid JSON block is found, log a warning and skip output-dependent actions.
2. **Comment output**: If `actions.comment_output` is true or `actions.add_comment` is true, post a comment on the issue with the task summary extracted from the structured output.
3. **Copilot review**: If `actions.copilot_review` is true and the structured output contains a `pr_number`, request a Copilot review on the PR using the REST API.
4. **Errand review task**: If `actions.review_profile_id` is set and the structured output contains a `pr_url` and `branch`, create a new errand Task with the review profile, passing the PR URL and branch in the description.
5. **Column transition**: If `actions.column_on_complete` is set, move the project item to the specified column. If either Copilot review or errand review task was triggered, use `column_on_complete` (expected to be "In Review"). If neither review option is configured, use `column_on_complete` as-is.

#### Scenario: Full completion with review

- **WHEN** a task completes with structured output containing `pr_number: 47` and `pr_url`, and the trigger has `{"comment_output": true, "copilot_review": true, "review_profile_id": "uuid", "column_on_complete": "In Review"}`
- **THEN** the updater posts a summary comment, requests Copilot review on PR #47, creates a review task with the review profile, and moves the issue to "In Review"

#### Scenario: Completion without review

- **WHEN** a task completes and the trigger has `{"comment_output": true, "column_on_complete": "In Review"}` but no `copilot_review` or `review_profile_id`
- **THEN** the updater posts a summary comment and moves the issue to "In Review" (no review actions)

#### Scenario: Completion with aborted status

- **WHEN** a task completes and the structured output has `status: "aborted"`
- **THEN** the updater posts the abort reason as a comment but does NOT request reviews, create review tasks, or transition the column

#### Scenario: No structured output found

- **WHEN** a task completes but the output does not contain a valid fenced JSON block
- **THEN** the updater logs a warning, posts a generic completion comment if `add_comment` is true, and does not perform review or column transition actions

### Requirement: GitHub comment on task failure

When a task transitions from `running` to `failed` and has an ExternalTaskRef with `source: "github"` and the trigger has `actions.add_comment: true`, the updater SHALL post a comment on the GitHub issue with the text `"Errand task failed (task ID: {task_id}). Error: {error_message}"`. The updater SHALL NOT perform column transitions or review actions on failure.

#### Scenario: Comment posted on task failure

- **WHEN** a task transitions to failed, has an ExternalTaskRef with source="github", and the trigger has actions `{"add_comment": true}`
- **THEN** the updater posts a failure comment on the GitHub issue

#### Scenario: No comment on failure when add_comment is false

- **WHEN** a task transitions to failed and the trigger has actions `{"add_comment": false}`
- **THEN** the updater does not post a comment

### Requirement: Create review task from structured output

When the trigger's `actions.review_profile_id` is set and the completed task's structured output contains `pr_url` and `branch`, the updater SHALL create a new Task with: `profile_id` set to the review profile UUID, title set to `"Review: {repo_owner}/{repo_name}#{pr_number}"`, description containing the PR URL, branch name, and original issue reference, and `created_by` set to `"github:review:{external_id}"`. The updater SHALL also create an ExternalTaskRef for the review task linking it to the same GitHub issue.

#### Scenario: Review task created

- **WHEN** a task completes with `pr_url: "https://github.com/acme/api/pull/47"`, `branch: "bug/fix-auth"`, and the trigger has `review_profile_id: "uuid"`
- **THEN** a new Task is created with the review profile, description containing the PR details, and an ExternalTaskRef linking to the original issue

#### Scenario: Review task not created when profile not configured

- **WHEN** a task completes and the trigger does not have `review_profile_id`
- **THEN** no review task is created
