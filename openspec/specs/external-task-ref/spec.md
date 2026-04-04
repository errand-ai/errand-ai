## ADDED Requirements

### Requirement: ExternalTaskRef data model

The system SHALL provide an `ExternalTaskRef` SQLAlchemy model with the following fields: `id` (UUID, primary key, server-generated), `task_id` (UUID, foreign key to `Task.id`, unique, not null), `trigger_id` (UUID, foreign key to `WebhookTrigger.id`, nullable — nullable because the trigger can be deleted after task creation), `source` (string, not null — e.g. "jira", "github"), `external_id` (string, not null — human-readable key such as "PROJ-123" or "owner/repo#42"), `external_url` (string, not null — full URL to the external item), `parent_id` (string, nullable — parent item key, e.g. epic key for a sub-task), `metadata` (JSON dict, default empty dict — source-specific IDs and data such as Jira numeric issue ID, GitHub node ID), `created_at` (datetime, server default UTC now), `updated_at` (datetime, server default UTC now, updated on modification). The model SHALL have a unique constraint on `(external_id, source)` to prevent duplicate tasks for the same external item.

#### Scenario: Create an ExternalTaskRef for a Jira issue

- **WHEN** an ExternalTaskRef is created with task_id=<uuid>, trigger_id=<uuid>, source="jira", external_id="PROJ-123", external_url="https://jira.example.com/browse/PROJ-123", metadata={"issue_id": "10042"}
- **THEN** the record is persisted with a generated UUID and null parent_id

#### Scenario: Deduplication constraint prevents duplicate external items

- **WHEN** an ExternalTaskRef with source="jira" and external_id="PROJ-123" already exists and a second ExternalTaskRef with the same source and external_id is inserted
- **THEN** the database SHALL raise a unique constraint violation

#### Scenario: Trigger deletion nullifies trigger_id

- **WHEN** a WebhookTrigger is deleted and an ExternalTaskRef references it via trigger_id
- **THEN** the ExternalTaskRef's trigger_id is set to null (the ref and its associated task remain intact)

#### Scenario: Task deletion cascades to ExternalTaskRef

- **WHEN** a Task is deleted and an ExternalTaskRef references it via task_id
- **THEN** the ExternalTaskRef record SHALL be deleted (cascade delete)

### Requirement: Alembic migration for ExternalTaskRef

The system SHALL include an Alembic migration that creates the `external_task_ref` table with all columns, the unique constraint on `(external_id, source)`, the unique constraint on `task_id`, the foreign key to `task` (cascade delete), and the foreign key to `webhook_trigger` (set null on delete). The migration SHALL be reversible.

#### Scenario: Migration applies cleanly

- **WHEN** `alembic upgrade head` is run on a database without the external_task_ref table
- **THEN** the table is created with all specified columns, constraints, and foreign keys

### Requirement: ExternalTaskRef creation on webhook task creation

The system SHALL create an ExternalTaskRef record whenever a task is created from a webhook trigger. The ExternalTaskRef MUST be created in the same database transaction as the Task to ensure atomicity.

#### Scenario: Task and ExternalTaskRef created together

- **WHEN** a webhook trigger creates a new task for Jira issue PROJ-456
- **THEN** both the Task record and the ExternalTaskRef record are committed in a single transaction

#### Scenario: ExternalTaskRef creation failure rolls back task

- **WHEN** the ExternalTaskRef insert fails (e.g. duplicate constraint violation)
- **THEN** the Task insert is also rolled back and no partial records exist

### Requirement: Lookup by task_id for completion callbacks

The system SHALL provide a lookup method to retrieve an ExternalTaskRef by `task_id`. This is used by the ExternalStatusUpdater to find the external reference when a task completes.

#### Scenario: Lookup existing ref by task_id

- **WHEN** an ExternalTaskRef exists for task_id=<uuid> and a lookup by that task_id is performed
- **THEN** the ExternalTaskRef record is returned with all fields populated

#### Scenario: Lookup non-existent ref by task_id

- **WHEN** no ExternalTaskRef exists for a given task_id and a lookup by that task_id is performed
- **THEN** the result is null (the task was not created from a webhook)

### Requirement: Lookup by external_id and source for deduplication

The system SHALL provide a lookup method to retrieve an ExternalTaskRef by the combination of `external_id` and `source`. This is used by the webhook receiver to check whether a task already exists for a given external item before creating a new one.

#### Scenario: Existing external item found

- **WHEN** an ExternalTaskRef with source="jira" and external_id="PROJ-123" exists and a lookup is performed with those values
- **THEN** the ExternalTaskRef record is returned, indicating the external item already has an associated task

#### Scenario: No existing external item

- **WHEN** no ExternalTaskRef with source="jira" and external_id="PROJ-789" exists and a lookup is performed
- **THEN** the result is null, indicating a new task should be created
