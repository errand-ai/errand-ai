## ADDED Requirements

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
