## MODIFIED Requirements

### Requirement: CRUD API for WebhookTrigger

The system SHALL expose the following REST endpoints for WebhookTrigger management. All endpoints MUST require admin role authorization.

- `GET /api/webhook-triggers` — list all triggers, returning an array of trigger objects
- `GET /api/webhook-triggers/{id}` — retrieve a single trigger by UUID
- `POST /api/webhook-triggers` — create a new trigger from request body, with source-specific validation for filters and actions
- `PUT /api/webhook-triggers/{id}` — update an existing trigger (partial update), with source-specific validation
- `DELETE /api/webhook-triggers/{id}` — delete a trigger

When `source` is `"github"`, the create and update endpoints SHALL validate filters against the GitHub-specific schema: `project_node_id` (string, required), `trigger_column` (string, required), `content_types` (list of strings, optional, valid values: "Issue", "PullRequest", "DraftIssue"). When `source` is `"github"`, the create and update endpoints SHALL validate actions against the GitHub-specific schema: `add_comment` (boolean), `comment_output` (boolean), `column_on_running` (string), `column_on_complete` (string), `copilot_review` (boolean), `review_profile_id` (UUID string), `project_field_id` (string), `column_options` (dict). When `source` is `"jira"`, existing validation rules SHALL continue to apply unchanged.

#### Scenario: Create a Jira trigger (unchanged)

- **WHEN** a POST request is made with `{"name": "Jira Bugs", "source": "jira", "filters": {"event_types": ["issue_created"]}, "actions": {"add_comment": true}}`
- **THEN** the response status is 201 and the trigger is created with existing Jira validation

#### Scenario: Create a GitHub trigger with valid filters

- **WHEN** a POST request is made with `{"name": "Platform Project", "source": "github", "filters": {"project_node_id": "PVT_abc", "trigger_column": "Ready"}, "actions": {"column_on_running": "In Progress"}}`
- **THEN** the response status is 201 and the trigger is created

#### Scenario: Create a GitHub trigger with missing required filter

- **WHEN** a POST request is made with `{"name": "Bad Trigger", "source": "github", "filters": {"trigger_column": "Ready"}}` (missing project_node_id)
- **THEN** the response status is 400 with a validation error

#### Scenario: Create a GitHub trigger with invalid action key

- **WHEN** a POST request is made with `{"source": "github", "actions": {"invalid_key": true}}`
- **THEN** the response status is 400 with a validation error

#### Scenario: Update a GitHub trigger actions

- **WHEN** a PUT request is made to update a GitHub trigger with `{"actions": {"copilot_review": true, "review_profile_id": "valid-uuid"}}`
- **THEN** the response status is 200 and the trigger's actions are updated

#### Scenario: List all triggers (unchanged)

- **WHEN** a GET request is made to `/api/webhook-triggers` by an admin user
- **THEN** the response status is 200 and the body contains an array of all WebhookTrigger objects including both Jira and GitHub triggers
