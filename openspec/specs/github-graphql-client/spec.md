## Requirements

### Requirement: GitHub GraphQL client with authentication

The system SHALL provide a `GitHubClient` class in `errand/platforms/github/client.py` that makes authenticated requests to the GitHub GraphQL API (`https://api.github.com/graphql`) and REST API (`https://api.github.com`). The client SHALL accept GitHub credentials (from `GitHubPlatform`) and use either a PAT directly or mint an installation access token for GitHub App auth. The client SHALL set headers `Authorization: Bearer <token>`, `Accept: application/vnd.github+json`, and `Content-Type: application/json`. The client SHALL raise descriptive errors for GraphQL error responses (extracting the `errors[].message` field).

#### Scenario: Client authenticates with PAT

- **WHEN** the client is initialized with PAT credentials
- **THEN** all requests use the PAT as the bearer token

#### Scenario: Client authenticates with GitHub App

- **WHEN** the client is initialized with GitHub App credentials
- **THEN** the client mints an installation access token and uses it as the bearer token

#### Scenario: GraphQL error response raises exception

- **WHEN** a GraphQL response contains an `errors` array
- **THEN** the client raises an exception with the error messages concatenated

### Requirement: Introspect project structure

The client SHALL provide a method to introspect a GitHub ProjectV2 given an organization login and project number. The method SHALL return the project's `node_id`, `title`, and all fields with their types. For `SingleSelectField` types (including the Status field), the method SHALL return each option's `id` and `name`. This is used at trigger configuration time to discover field IDs and column option IDs.

#### Scenario: Introspect organization project

- **WHEN** `introspect_project(org="acme", project_number=5)` is called
- **THEN** the client returns the project node ID, title, and all fields including Status options like `[{"id": "abc", "name": "Backlog"}, {"id": "def", "name": "Ready"}, ...]`

#### Scenario: Project not found

- **WHEN** `introspect_project()` is called with a non-existent project number
- **THEN** the client raises an error indicating the project was not found

#### Scenario: Insufficient permissions

- **WHEN** the GitHub credentials lack the `project` scope or organization projects permission
- **THEN** the client raises an error indicating insufficient permissions

### Requirement: Resolve issue from node ID

The client SHALL provide a method to resolve a GitHub issue's full details from its node ID. The method SHALL query the GraphQL API using the `node` query with inline fragments for `Issue` and return: `number`, `title`, `body`, `state`, `url` (HTML URL), `repository.name`, `repository.owner.login`, `labels` (list of label name strings), and `assignees` (list of login strings).

#### Scenario: Resolve issue node ID

- **WHEN** `resolve_issue(node_id="I_kwDOGH5678")` is called
- **THEN** the client returns issue details including number, title, repo owner/name, labels, and URL

#### Scenario: Node ID is not an Issue

- **WHEN** `resolve_issue(node_id="PVTI_...")` is called with a non-Issue node ID
- **THEN** the client raises an error indicating the node is not an Issue

### Requirement: Find project item for an issue

The client SHALL provide a method to find the ProjectV2Item ID for a given issue within a specific project. The method SHALL query the issue's `projectItems` and filter by the target project's node ID. The method SHALL return the ProjectV2Item `node_id` and current Status field value (name and option ID).

#### Scenario: Issue found in project

- **WHEN** `find_project_item(issue_node_id="I_...", project_node_id="PVT_...")` is called and the issue is in the project
- **THEN** the client returns the ProjectV2Item ID and current status

#### Scenario: Issue not in project

- **WHEN** `find_project_item()` is called and the issue is not a member of the specified project
- **THEN** the client returns None

### Requirement: Update project item status (column transition)

The client SHALL provide a method to update a ProjectV2Item's Status field value using the `updateProjectV2ItemFieldValue` GraphQL mutation. The method SHALL accept: `project_id`, `item_id`, `field_id`, and `option_id`. These IDs are obtained from the cached project structure (at trigger config time) and the ExternalTaskRef metadata (at webhook processing time).

#### Scenario: Move item to "In Progress"

- **WHEN** `update_item_status(project_id="PVT_...", item_id="PVTI_...", field_id="PVTSSF_...", option_id="abc123")` is called
- **THEN** the GraphQL mutation executes and the item's Status field is updated

#### Scenario: Invalid item ID

- **WHEN** `update_item_status()` is called with a non-existent item_id
- **THEN** the client raises an error from the GraphQL response

### Requirement: Add comment to issue

The client SHALL provide a method to add a comment to a GitHub issue or pull request using the `addComment` GraphQL mutation. The method SHALL accept a `subject_id` (issue or PR node ID) and `body` (markdown string).

#### Scenario: Comment added successfully

- **WHEN** `add_comment(subject_id="I_...", body="Task completed.")` is called
- **THEN** the comment is posted and the method returns the comment URL

#### Scenario: Comment body with markdown

- **WHEN** `add_comment()` is called with a body containing markdown formatting
- **THEN** the comment is posted with the markdown preserved

### Requirement: Request pull request review

The client SHALL provide a method to request a review on a pull request using the REST API endpoint `POST /repos/{owner}/{repo}/pulls/{pull_number}/requested_reviewers`. The method SHALL accept an owner, repo, pull number, and list of reviewer logins. This is used to request Copilot review (login: `"copilot"`).

#### Scenario: Request Copilot review

- **WHEN** `request_review(owner="acme", repo="api", pull_number=47, reviewers=["copilot"])` is called
- **THEN** the REST API is called and the review request is created

#### Scenario: Reviewer not found

- **WHEN** `request_review()` is called with an invalid reviewer login
- **THEN** the client logs a warning (GitHub returns 422) but does not raise an exception
