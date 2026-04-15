## Requirements

### Requirement: Parse GitHub projects_v2_item webhook payload

The system SHALL accept GitHub `projects_v2_item` webhook JSON payloads and extract the following fields: `action` (top-level string), `projects_v2_item.node_id` (ProjectV2Item ID), `projects_v2_item.project_node_id` (Project ID), `projects_v2_item.content_node_id` (Issue/PR node ID), `projects_v2_item.content_type` (string: "Issue", "PullRequest", or "DraftIssue"), `changes.field_value.field_name` (string), `changes.field_value.from.name` (string), `changes.field_value.to.name` (string), `organization.login` (string), and `sender.login` (string). The system SHALL reject payloads missing required fields (`action`, `projects_v2_item`) with a logged warning and no task creation.

#### Scenario: Valid projects_v2_item edited payload

- **WHEN** a webhook payload arrives with `action: "edited"` and a complete `projects_v2_item` object with `changes.field_value`
- **THEN** the system extracts all filter-relevant fields and proceeds to filter evaluation

#### Scenario: Payload missing projects_v2_item

- **WHEN** a webhook payload arrives with `action: "edited"` but no `projects_v2_item` key
- **THEN** the system logs a warning and does not create a task

#### Scenario: Non-edited action ignored

- **WHEN** a webhook payload arrives with `action: "created"` or `action: "deleted"`
- **THEN** the system skips processing without error (only `edited` actions with Status field changes are relevant)

### Requirement: Evaluate project_node_id filter

The system SHALL match the payload's `projects_v2_item.project_node_id` against the trigger's `filters.project_node_id`. A match occurs when the values are identical strings. This filter is required — if not configured on the trigger, the filter SHALL fail.

#### Scenario: Project ID matches

- **WHEN** the payload has `project_node_id: "PVT_abc123"` and the trigger's filters contain `project_node_id: "PVT_abc123"`
- **THEN** the project filter passes

#### Scenario: Project ID does not match

- **WHEN** the payload has `project_node_id: "PVT_abc123"` and the trigger's filters contain `project_node_id: "PVT_xyz789"`
- **THEN** the project filter fails and the trigger is skipped

#### Scenario: Project ID filter not configured

- **WHEN** the trigger's filters do not contain a `project_node_id` key
- **THEN** the project filter fails and the trigger is skipped

### Requirement: Evaluate trigger_column filter

The system SHALL match the payload's `changes.field_value.to.name` against the trigger's `filters.trigger_column` (case-insensitive comparison). The system SHALL also verify that `changes.field_value.field_name` is `"Status"`. If either condition fails, the filter SHALL fail. If the trigger's `trigger_column` is not configured, the filter SHALL fail.

#### Scenario: Column matches trigger_column

- **WHEN** the payload's field_value has `field_name: "Status"` and `to.name: "Ready"`, and the trigger's filters contain `trigger_column: "Ready"`
- **THEN** the trigger_column filter passes

#### Scenario: Column does not match

- **WHEN** the payload's field_value has `to.name: "In Progress"` and the trigger's filters contain `trigger_column: "Ready"`
- **THEN** the trigger_column filter fails

#### Scenario: Non-Status field change ignored

- **WHEN** the payload's field_value has `field_name: "Priority"` (not "Status")
- **THEN** the trigger_column filter fails regardless of the to.name value

#### Scenario: Case-insensitive column matching

- **WHEN** the payload's field_value has `to.name: "ready"` and the trigger's filters contain `trigger_column: "Ready"`
- **THEN** the trigger_column filter passes

### Requirement: Evaluate content_types filter

The system SHALL match the payload's `projects_v2_item.content_type` against the trigger's `filters.content_types` list. A match occurs when the content_type is present in the list. If the trigger's `content_types` list is empty, null, or not configured, the filter SHALL default to `["Issue"]` (only issues, not PRs or draft issues).

#### Scenario: Content type matches

- **WHEN** the payload has `content_type: "Issue"` and the trigger's filters contain `content_types: ["Issue"]`
- **THEN** the content_types filter passes

#### Scenario: Content type does not match

- **WHEN** the payload has `content_type: "PullRequest"` and the trigger's filters contain `content_types: ["Issue"]`
- **THEN** the content_types filter fails

#### Scenario: Default content_types when not configured

- **WHEN** the trigger's filters do not contain a `content_types` key and the payload has `content_type: "Issue"`
- **THEN** the content_types filter passes (defaults to `["Issue"]`)

### Requirement: Resolve issue details via GraphQL

After all filters pass, the system SHALL use the `content_node_id` from the payload to query the GitHub GraphQL API and resolve the full issue details: `number`, `title`, `body`, `url` (HTML URL), `repository.name`, `repository.owner.login`, `labels` (list of label names), and `assignees` (list of login names). The system SHALL use the GitHub credentials associated with the trigger's platform configuration. If the GraphQL query fails, the system SHALL log the error and not create a task.

#### Scenario: Issue resolved successfully

- **WHEN** the content_node_id resolves to an Issue with number 42, title "Fix auth redirect", in repo "org/api-server"
- **THEN** the system captures all issue metadata for task creation

#### Scenario: GraphQL query fails

- **WHEN** the GraphQL query to resolve the content_node_id returns an error (auth failure, network error, etc.)
- **THEN** the system logs the error with the content_node_id and does not create a task

#### Scenario: Content node resolves to DraftIssue

- **WHEN** the content_node_id resolves to a DraftIssue (no repository association)
- **THEN** the system logs a warning and does not create a task (DraftIssues cannot be implemented)

### Requirement: Create task from GitHub Projects webhook

After filters pass and issue details are resolved, the system SHALL create a Task with: title set to `"{repo_owner}/{repo_name}#{issue_number}: {issue_title}"`, description composed of the issue body plus metadata (repo, labels, assignees) plus the trigger's `task_prompt` (if configured), profile_id from the trigger, and `created_by` set to `"github:{repo_owner}/{repo_name}#{issue_number}"`. The system SHALL also create an `ExternalTaskRef` with `source: "github"`, `external_id` set to `"{repo_owner}/{repo_name}#{issue_number}"`, `external_url` set to the issue HTML URL, `trigger_id` from the matched trigger, and `metadata_` containing `project_node_id`, `item_node_id`, `content_node_id`, `repo_owner`, `repo_name`, and `issue_labels`.

#### Scenario: Task created successfully

- **WHEN** the webhook for issue #42 "Fix auth redirect" in repo "acme/api-server" passes all filters
- **THEN** a Task is created with title `"acme/api-server#42: Fix auth redirect"`, an ExternalTaskRef linking to the issue, and tagged with "github"

#### Scenario: Duplicate task prevention

- **WHEN** a webhook fires for an issue that already has an ExternalTaskRef with matching `external_id` and `trigger_id`
- **THEN** the system logs a warning and does not create a duplicate task

#### Scenario: Task includes trigger task_prompt

- **WHEN** the matched trigger has `task_prompt: "Focus on performance implications"`
- **THEN** the task description includes this prompt appended after the issue metadata

### Requirement: Comment on issue after task creation

After creating a task, the system SHALL post a comment on the GitHub issue using the GraphQL `addComment` mutation. The comment SHALL include the errand task ID and a link to the task in the errand UI. If the comment fails to post, the system SHALL log the error but not fail the task creation (the task is already created).

#### Scenario: Comment posted successfully

- **WHEN** a task is created for issue #42
- **THEN** a comment is posted on the issue: "Errand task created: [task-id](https://errand-url/tasks/task-id)"

#### Scenario: Comment posting fails

- **WHEN** the GraphQL mutation to add a comment returns an error
- **THEN** the system logs the error and the task remains created (no rollback)
