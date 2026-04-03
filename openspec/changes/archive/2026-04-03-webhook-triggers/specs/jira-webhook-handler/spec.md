## Purpose

Jira-specific webhook payload processing: parses Jira webhook JSON, evaluates trigger filters, and creates errand tasks with external references on match.

## ADDED Requirements

### Requirement: Parse Jira webhook payload
The system SHALL accept Jira webhook JSON payloads and extract the following fields for filter evaluation: `webhookEvent` (top-level string), `issue.fields.issuetype.name`, `issue.fields.labels` (array of strings), `issue.fields.project.key`, `issue.key`, `issue.fields.summary`, `issue.fields.description`, `issue.fields.reporter.displayName`, `issue.fields.priority.name`, `issue.self`, `issue.fields.parent.key` (nullable), and `changelog` (present on update events). The system SHALL reject payloads missing required fields (`webhookEvent`, `issue.key`, `issue.fields`) with a logged warning and no task creation.

#### Scenario: Valid Jira issue_created payload
- **WHEN** a webhook payload arrives with `webhookEvent: "jira:issue_created"` and a complete `issue` object
- **THEN** the system extracts all filter-relevant fields and proceeds to filter evaluation

#### Scenario: Payload missing issue fields
- **WHEN** a webhook payload arrives with `webhookEvent: "jira:issue_created"` but no `issue` key
- **THEN** the system logs a warning and does not create a task

#### Scenario: Payload with unknown webhookEvent
- **WHEN** a webhook payload arrives with a `webhookEvent` value not matching any configured trigger
- **THEN** the system skips processing for that trigger without error

### Requirement: Evaluate event_types filter
The system SHALL match the payload's `webhookEvent` field against the trigger's `event_types` list. A match occurs when the `webhookEvent` value is present in the list. If the trigger's `event_types` list is empty or null, the filter SHALL be treated as matching all events.

#### Scenario: Event type matches
- **WHEN** the payload has `webhookEvent: "jira:issue_created"` and the trigger's `event_types` contains `"jira:issue_created"`
- **THEN** the event_types filter passes

#### Scenario: Event type does not match
- **WHEN** the payload has `webhookEvent: "jira:issue_updated"` and the trigger's `event_types` contains only `"jira:issue_created"`
- **THEN** the event_types filter fails and the trigger is skipped

#### Scenario: Empty event_types filter
- **WHEN** the trigger's `event_types` is an empty list
- **THEN** the event_types filter passes for any webhookEvent value

### Requirement: Evaluate issue_types filter
The system SHALL match the payload's `issue.fields.issuetype.name` against the trigger's `issue_types` list (case-insensitive comparison). Supported values include "Feature", "Task", "Story", "Bug", and any custom issue type name. If the trigger's `issue_types` list is empty or null, the filter SHALL match all issue types.

#### Scenario: Issue type matches
- **WHEN** the payload's issue type is "Story" and the trigger's `issue_types` contains "Story"
- **THEN** the issue_types filter passes

#### Scenario: Case-insensitive matching
- **WHEN** the payload's issue type is "bug" and the trigger's `issue_types` contains "Bug"
- **THEN** the issue_types filter passes

#### Scenario: Issue type does not match
- **WHEN** the payload's issue type is "Epic" and the trigger's `issue_types` contains only "Task" and "Bug"
- **THEN** the issue_types filter fails and the trigger is skipped

### Requirement: Evaluate labels filter
The system SHALL match when any label in `issue.fields.labels` is present in the trigger's `labels` list. For `jira:issue_updated` events, the system SHALL additionally check the `changelog.items` array for an entry with `field: "labels"` and verify that a matching label appears in the `toString` value but not in the `fromString` value, confirming the label was just added. If the trigger's `labels` list is empty or null, the filter SHALL match all labels.

#### Scenario: Label matches on issue_created
- **WHEN** the event is `jira:issue_created`, the issue has labels `["errand", "frontend"]`, and the trigger's `labels` contains `"errand"`
- **THEN** the labels filter passes

#### Scenario: Label just added on issue_updated
- **WHEN** the event is `jira:issue_updated`, the changelog shows label `"errand"` was added (in `toString` but not `fromString`), and the trigger's `labels` contains `"errand"`
- **THEN** the labels filter passes

#### Scenario: Label already existed on issue_updated
- **WHEN** the event is `jira:issue_updated`, the issue has label `"errand"` but the changelog does not show it was just added
- **THEN** the labels filter fails for this trigger

#### Scenario: Empty labels filter
- **WHEN** the trigger's `labels` list is empty
- **THEN** the labels filter passes for any issue regardless of its labels

### Requirement: Evaluate projects filter
The system SHALL match the payload's `issue.fields.project.key` against the trigger's `projects` list (exact, case-sensitive comparison). If the trigger's `projects` list is empty or null, the filter SHALL match all projects.

#### Scenario: Project matches
- **WHEN** the issue's project key is "WEBAPP" and the trigger's `projects` contains "WEBAPP"
- **THEN** the projects filter passes

#### Scenario: Project does not match
- **WHEN** the issue's project key is "MOBILE" and the trigger's `projects` contains only "WEBAPP"
- **THEN** the projects filter fails and the trigger is skipped

### Requirement: Create errand task on filter match
When all configured filters pass for a trigger, the system SHALL create a new errand task with: `title` set to `"{issue_key}: {issue_summary}"`, `description` containing the issue description text plus metadata (reporter display name, priority name, and linked issue keys if present), `profile_id` from the trigger's configured profile, `status` set to `"pending"`, a tag `"jira"` applied to the task, and `created_by` set to `"jira:{issue_key}"`. The system MUST NOT create duplicate tasks for the same issue key and trigger combination.

#### Scenario: Task created on matching trigger
- **WHEN** all filters pass for a trigger matching issue PROJ-123 with summary "Fix login bug"
- **THEN** a task is created with title "PROJ-123: Fix login bug", status "pending", tag "jira", and the trigger's profile assigned

#### Scenario: Task description includes metadata
- **WHEN** a task is created for an issue with reporter "Jane Doe", priority "High", and linked issues "PROJ-100, PROJ-101"
- **THEN** the task description contains the issue description text, reporter name, priority, and linked issue keys

#### Scenario: Duplicate prevention
- **WHEN** a webhook fires for issue PROJ-123 and a task already exists with `created_by: "jira:PROJ-123"` for the same trigger
- **THEN** no new task is created

### Requirement: Create ExternalTaskRef on task creation
When an errand task is created from a Jira webhook, the system SHALL create an `ExternalTaskRef` record with: `source` set to `"jira"`, `external_id` set to the issue key (e.g. "PROJ-123"), `external_url` set to the issue's `self` link, `parent_id` set to the parent issue key if `issue.fields.parent.key` is present (null otherwise), and `metadata` containing `project_key` (from `issue.fields.project.key`) and `cloud_id` (from the trigger's associated Jira credential).

#### Scenario: ExternalTaskRef created with parent
- **WHEN** a task is created for issue PROJ-456 which has parent PROJ-100
- **THEN** an ExternalTaskRef is created with source "jira", external_id "PROJ-456", parent_id "PROJ-100", and metadata including the project key and cloud_id

#### Scenario: ExternalTaskRef created without parent
- **WHEN** a task is created for issue PROJ-789 which has no parent
- **THEN** an ExternalTaskRef is created with source "jira", external_id "PROJ-789", parent_id null, and metadata including the project key and cloud_id
