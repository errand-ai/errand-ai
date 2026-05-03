## MODIFIED Requirements

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
