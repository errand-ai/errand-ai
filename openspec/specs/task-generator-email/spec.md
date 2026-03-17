## Purpose

Generic task generator data model and API for managing trigger configurations that automatically create tasks from external sources. Starting with email, extensible to webhook and other trigger types.

## Requirements

### Requirement: Task generator data model
The system SHALL store task generator configurations in a `task_generator` database table with the following fields: `id` (UUID, primary key), `type` (text, unique), `enabled` (boolean, default false), `profile_id` (UUID, nullable FK to task profiles), `config` (JSON, type-specific configuration), `created_at`, `updated_at`.

#### Scenario: Email task generator record created
- **WHEN** an admin saves email trigger settings for the first time
- **THEN** a `task_generator` record is created with `type="email"` and the configured settings

#### Scenario: Config field stores type-specific settings
- **WHEN** an email task generator is saved with poll_interval=120 and a task_prompt
- **THEN** the `config` JSON contains `{"poll_interval": 120, "task_prompt": "..."}`

#### Scenario: Type uniqueness enforced
- **WHEN** a second task generator with `type="email"` is created
- **THEN** the system rejects it with a uniqueness constraint error

### Requirement: Task generator API endpoints
The system SHALL provide REST API endpoints for managing task generators.

#### Scenario: List task generators
- **WHEN** `GET /api/task-generators` is called
- **THEN** all task generator records are returned

#### Scenario: Get email task generator
- **WHEN** `GET /api/task-generators/email` is called
- **THEN** the email task generator configuration is returned, or 404 if not configured

#### Scenario: Create or update email task generator
- **WHEN** `PUT /api/task-generators/email` is called with configuration data
- **THEN** the email task generator is created or updated (upsert)

### Requirement: Migration from email credentials
When the database migration runs, existing email platform credentials that contain `email_profile` and `poll_interval` fields SHALL be migrated to a new `task_generator` record with `type="email"` and `enabled=true`. The migrated fields SHALL be removed from the platform credential data.

#### Scenario: Existing email credentials migrated
- **WHEN** the migration runs and email credentials contain `email_profile` and `poll_interval`
- **THEN** a task generator record is created with the migrated values and `enabled=true`
- **AND** the email credential no longer contains `email_profile` or `poll_interval`

#### Scenario: No email credentials to migrate
- **WHEN** the migration runs and no email credentials exist
- **THEN** no task generator record is created
