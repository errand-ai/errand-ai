## ADDED Requirements

### Requirement: WebhookTrigger data model

The system SHALL provide a `WebhookTrigger` SQLAlchemy model with the following fields: `id` (UUID, primary key, server-generated), `name` (string, unique, not null), `enabled` (boolean, default true), `source` (string, not null — values such as "jira", "github", etc.), `profile_id` (UUID, foreign key to `TaskProfile.id`, nullable), `filters` (JSON dict, default empty dict), `actions` (JSON dict, default empty dict), `task_prompt` (string, nullable — override prompt template for tasks created by this trigger), `webhook_secret` (string, nullable — stored encrypted at rest, server-generated), `cloud_webhook_url` (string, nullable — populated from cloud's `POST /api/endpoints` response on successful registration), `cloud_endpoint_token` (string, nullable — populated alongside `cloud_webhook_url`, used for token-based revocation), `created_at` (datetime, server default UTC now), `updated_at` (datetime, server default UTC now, updated on modification). The model SHALL have a relationship to `TaskProfile` (many-to-one, nullable). The model SHALL have a one-to-many relationship to `ExternalTaskRef` via the `trigger_id` foreign key.

#### Scenario: Create a WebhookTrigger with minimal fields

- **WHEN** a WebhookTrigger is created with name="Jira Bug Tracker" and source="jira"
- **THEN** the record is persisted with a generated UUID, enabled=true, empty filters and actions dicts, and null profile_id, task_prompt, cloud_webhook_url, and cloud_endpoint_token
- **THEN** the record SHALL be persisted with a server-generated `webhook_secret`

#### Scenario: Cloud registration populates URL and token
- **WHEN** a WebhookTrigger is registered with errand-cloud and the registration succeeds
- **THEN** `cloud_webhook_url` SHALL be set to the URL returned by `POST /api/endpoints`
- **THEN** `cloud_endpoint_token` SHALL be set to the token returned by `POST /api/endpoints`

#### Scenario: Cloud disconnect clears URL and token
- **WHEN** the user disconnects from errand-cloud
- **THEN** `cloud_webhook_url` and `cloud_endpoint_token` SHALL be set to null on every WebhookTrigger record for the affected integrations

#### Scenario: Name uniqueness enforced

- **WHEN** a WebhookTrigger with name="My Trigger" already exists and a second trigger with name="My Trigger" is inserted
- **THEN** the database SHALL raise a unique constraint violation

#### Scenario: Profile relationship is nullable

- **WHEN** a WebhookTrigger is created with profile_id=null
- **THEN** the trigger is valid and its profile relationship returns null

#### Scenario: Deleting a trigger cascade-nullifies ExternalTaskRef

- **WHEN** a WebhookTrigger is deleted and ExternalTaskRef records reference it via trigger_id
- **THEN** the trigger_id on those ExternalTaskRef records SHALL be set to null (not deleted)

### Requirement: Alembic migration for WebhookTrigger

The system SHALL include Alembic migrations that create the `webhook_trigger` table with all columns including `cloud_webhook_url` and `cloud_endpoint_token`, the unique constraint on `name`, and the foreign key to `task_profile`. Migrations SHALL be reversible.

#### Scenario: Migration adds cloud columns
- **WHEN** the Alembic upgrade runs against a database that does not yet have `cloud_webhook_url` or `cloud_endpoint_token` columns on `webhook_trigger`
- **THEN** the upgrade SHALL add both columns as nullable strings
- **THEN** the corresponding downgrade SHALL drop both columns

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
- **THEN** the response status is 422 with a validation error

#### Scenario: Create a GitHub trigger with invalid action key

- **WHEN** a POST request is made with `{"source": "github", "actions": {"invalid_key": true}}`
- **THEN** the response status is 422 with a validation error

#### Scenario: Update a GitHub trigger actions

- **WHEN** a PUT request is made to update a GitHub trigger with `{"actions": {"copilot_review": true, "review_profile_id": "valid-uuid"}}`
- **THEN** the response status is 200 and the trigger's actions are updated

#### Scenario: List all triggers (unchanged)

- **WHEN** a GET request is made to `/api/webhook-triggers` by an admin user
- **THEN** the response status is 200 and the body contains an array of all WebhookTrigger objects including both Jira and GitHub triggers

#### Scenario: Get a single trigger

- **WHEN** a GET request is made to `/api/webhook-triggers/{id}` with a valid UUID
- **THEN** the response status is 200 and the body contains the trigger object with all fields

#### Scenario: Get a non-existent trigger

- **WHEN** a GET request is made to `/api/webhook-triggers/{id}` with a UUID that does not exist
- **THEN** the response status is 404

#### Scenario: Update a trigger

- **WHEN** a PUT request is made to `/api/webhook-triggers/{id}` with body `{"enabled": false}`
- **THEN** the response status is 200 and the trigger's enabled field is updated to false

#### Scenario: Delete a trigger

- **WHEN** a DELETE request is made to `/api/webhook-triggers/{id}` with a valid UUID
- **THEN** the response status is 204 and the trigger is removed from the database

#### Scenario: Non-admin access denied

- **WHEN** a non-admin user makes any request to the webhook-triggers endpoints
- **THEN** the response status is 403

### Requirement: Filter schema validation

The `filters` JSON field SHALL be validated on create and update. The allowed keys are: `event_types` (array of strings), `issue_types` (array of strings), `labels` (array of strings), `projects` (array of strings). Any key not in this set SHALL cause a 422 validation error. All values MUST be arrays of strings. An empty dict is valid (matches all events).

#### Scenario: Valid filter accepted

- **WHEN** a trigger is created with filters `{"event_types": ["issue_created", "issue_updated"], "projects": ["PROJ"]}`
- **THEN** the trigger is created successfully

#### Scenario: Unknown filter key rejected

- **WHEN** a trigger is created with filters `{"priority": ["high"]}`
- **THEN** the response status is 422 with an error indicating "priority" is not a valid filter key

#### Scenario: Non-array filter value rejected

- **WHEN** a trigger is created with filters `{"event_types": "issue_created"}`
- **THEN** the response status is 422 with an error indicating the value must be an array

### Requirement: Action schema validation

The `actions` JSON field SHALL be validated on create and update. The allowed keys are: `assign_to` (string — username or identifier to assign the external item to), `add_comment` (boolean — whether to post status comments back to the source), `add_label` (string — label to add to the external item), `transition_on_complete` (string — target status/transition name when the task completes), `comment_output` (boolean — whether to include task output in the completion comment). Any key not in this set SHALL cause a 422 validation error. An empty dict is valid (no actions configured).

#### Scenario: Valid actions accepted

- **WHEN** a trigger is created with actions `{"add_comment": true, "transition_on_complete": "Done"}`
- **THEN** the trigger is created successfully

#### Scenario: Unknown action key rejected

- **WHEN** a trigger is created with actions `{"send_email": true}`
- **THEN** the response status is 422 with an error indicating "send_email" is not a valid action key

#### Scenario: Wrong action value type rejected

- **WHEN** a trigger is created with actions `{"add_comment": "yes"}`
- **THEN** the response status is 422 with an error indicating add_comment must be a boolean
