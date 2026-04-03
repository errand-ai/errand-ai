## Purpose

Server-side Jira REST API calls for completion callbacks, using httpx with Bearer token auth against the Atlassian Cloud gateway.

## ADDED Requirements

### Requirement: Jira API client configuration
The system SHALL make Jira REST API calls using httpx with Bearer token authentication against the Atlassian Cloud gateway at `https://api.atlassian.com/ex/jira/{cloud_id}/`. The `cloud_id` and `api_token` SHALL be loaded from `PlatformCredential` with `platform_id="jira"`. All requests SHALL include the header `Authorization: Bearer {api_token}` and `Content-Type: application/json`.

#### Scenario: API client initializes with valid credentials
- **WHEN** a Jira completion action is triggered and valid Jira credentials exist
- **THEN** the httpx client is configured with the correct base URL using the stored cloud_id and the Bearer token from the stored api_token

#### Scenario: Credentials not configured
- **WHEN** a Jira completion action is triggered but no PlatformCredential exists for platform_id "jira"
- **THEN** the system logs a warning and skips all Jira actions for this task

### Requirement: Add comment action
The system SHALL support an `add_comment` action that posts task output as a comment on the originating Jira issue. The comment SHALL be sent via `POST /rest/api/3/issue/{issueKey}/comment` with the body in Atlassian Document Format (ADF). The task output text SHALL be truncated to 30KB before wrapping in ADF structure (Jira enforces a ~32KB comment limit; the 30KB threshold leaves margin for the ADF wrapper). The ADF body SHALL use a `doc` node containing a `paragraph` node with the output as a `text` node.

#### Scenario: Comment added with task output
- **WHEN** the add_comment action runs for issue PROJ-123 with task output "Analysis complete: 5 issues found"
- **THEN** a POST request is sent to `/rest/api/3/issue/PROJ-123/comment` with an ADF body containing the output text

#### Scenario: Large output truncated
- **WHEN** the add_comment action runs with task output exceeding 30KB
- **THEN** the output is truncated to 30KB before being wrapped in ADF and posted as a comment

#### Scenario: Comment on non-existent issue
- **WHEN** the add_comment action runs for an issue key that no longer exists in Jira
- **THEN** the system logs the error and stores it in ExternalTaskRef metadata

### Requirement: Transition on complete action
The system SHALL support a `transition_on_complete` action that transitions the Jira issue to a specified status when the errand task completes. The system SHALL first call `GET /rest/api/3/issue/{issueKey}/transitions` to retrieve available transitions and find the transition whose `name` matches the configured target transition name (case-insensitive). The system SHALL then call `POST /rest/api/3/issue/{issueKey}/transitions` with the matched transition ID. If no matching transition is found, the system SHALL log a warning including the available transition names and skip the transition.

#### Scenario: Successful transition
- **WHEN** the transition_on_complete action runs for issue PROJ-123 with target transition "Done" and "Done" is an available transition
- **THEN** the system retrieves transitions, finds the "Done" transition ID, and posts the transition request

#### Scenario: Target transition not available
- **WHEN** the transition_on_complete action runs with target transition "Deployed" but the available transitions are "In Progress", "Done", and "Won't Do"
- **THEN** the system logs a warning listing the available transitions and does not attempt the transition

#### Scenario: Case-insensitive transition matching
- **WHEN** the configured target transition is "done" and the available transition name is "Done"
- **THEN** the system matches the transition successfully

### Requirement: Assign to service account action
The system SHALL support an `assign_to` action that assigns the Jira issue to the service account. The system SHALL resolve the service account's Atlassian account ID by searching for the user via `GET /rest/api/3/user/search?query={service_account_email}` using the email from PlatformCredential. The resolved account ID SHALL be cached for the lifetime of the process to avoid repeated lookups. The system SHALL then call `PUT /rest/api/3/issue/{issueKey}/assignee` with the resolved account ID.

#### Scenario: Assign to service account
- **WHEN** the assign_to action runs for issue PROJ-123 and the service account email resolves to account ID "abc123"
- **THEN** a PUT request is sent to `/rest/api/3/issue/PROJ-123/assignee` with `{"accountId": "abc123"}`

#### Scenario: Account ID cached after first resolution
- **WHEN** the assign_to action runs for a second issue after the account ID was previously resolved
- **THEN** the cached account ID is used without making another user search API call

#### Scenario: Service account email not found
- **WHEN** the user search returns no results for the configured service account email
- **THEN** the system logs an error and skips the assignment

### Requirement: Add label action
The system SHALL support an `add_label` action that adds a specified label to the Jira issue. The system SHALL call `PUT /rest/api/3/issue/{issueKey}` with an update payload that appends the label to the issue's labels array using the `{"update": {"labels": [{"add": "{label}"}]}}` format.

#### Scenario: Label added to issue
- **WHEN** the add_label action runs for issue PROJ-123 with label "errand-processed"
- **THEN** a PUT request is sent to `/rest/api/3/issue/PROJ-123` adding "errand-processed" to the labels

#### Scenario: Label already exists on issue
- **WHEN** the add_label action runs with a label that already exists on the issue
- **THEN** the Jira API handles the duplicate gracefully (no error) and the system completes successfully

### Requirement: Error handling for Jira actions
The system SHALL NOT retry failed Jira API calls automatically. On any action failure, the system SHALL log the error (including HTTP status code and response body) and store the error message in the `ExternalTaskRef.metadata` field for debugging. If the API returns HTTP 401 (invalid credentials), the system SHALL log a warning indicating invalid Jira credentials and skip all remaining actions for the current task.

#### Scenario: API call fails with server error
- **WHEN** a Jira API call returns HTTP 500
- **THEN** the error is logged, stored in ExternalTaskRef metadata, and no retry is attempted

#### Scenario: Invalid credentials (401)
- **WHEN** the first Jira API call returns HTTP 401
- **THEN** the system logs a warning about invalid credentials and skips all remaining actions for this task

#### Scenario: Network timeout
- **WHEN** a Jira API call times out
- **THEN** the error is logged, stored in ExternalTaskRef metadata, and no retry is attempted

#### Scenario: Error stored in ExternalTaskRef
- **WHEN** any Jira action fails with an error
- **THEN** the ExternalTaskRef.metadata is updated with a key describing the failed action and the error message
