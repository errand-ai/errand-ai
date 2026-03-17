## MODIFIED Requirements

### Requirement: Email poller background task
The system SHALL run an email poller as an `asyncio.create_task()` in the main server lifespan. The poller SHALL load email platform credentials on each cycle for IMAP connection details. The poller SHALL load task generation settings (profile, poll interval, task prompt) from the `task_generator` record with `type="email"`. If no email credentials are configured or the email task generator is not enabled, the poller SHALL sleep and retry. The poller SHALL run continuously until the application shuts down.

#### Scenario: Poller starts with application
- **WHEN** the FastAPI application starts, email platform credentials are configured, and the email task generator is enabled
- **THEN** the email poller begins monitoring the configured mailbox

#### Scenario: Poller waits when email unconfigured
- **WHEN** the FastAPI application starts and no email platform credentials are configured
- **THEN** the email poller sleeps and periodically checks for credentials

#### Scenario: Poller waits when trigger disabled
- **WHEN** the FastAPI application starts, email credentials exist, but the email task generator is disabled
- **THEN** the email poller sleeps and periodically checks for the generator to be enabled

#### Scenario: Poller stops on shutdown
- **WHEN** the FastAPI application receives a shutdown signal
- **THEN** the email poller cancels cleanly and closes any IMAP connections

### Requirement: Task creation from email
For each unread message, the poller SHALL create a task with: `title` derived from the email subject, `description` containing email metadata (from, to, date, subject), the markdown body, and the task prompt (if configured) appended as additional instructions. The `profile_id` SHALL be set to the task generator's configured profile (or null for Default). The `created_by` SHALL be set to `"email_poller"`. The `status` SHALL be `"pending"`. The poller SHALL publish a `task_created` WebSocket event for each created task.

#### Scenario: Task created from email with task prompt
- **WHEN** a new unread email arrives and the email task generator has a task prompt configured
- **THEN** a task is created with the email content in the description followed by the task prompt as additional instructions

#### Scenario: Task created from email without task prompt
- **WHEN** a new unread email arrives and the email task generator has no task prompt
- **THEN** a task is created with only the email content in the description (existing behavior)

#### Scenario: Task uses configured profile
- **WHEN** a task is created from email and the email task generator has a profile selected
- **THEN** the task's `profile_id` is set to the generator's configured profile

#### Scenario: Task uses Default profile
- **WHEN** a task is created from email and the email task generator has no profile selected
- **THEN** the task's `profile_id` is null (uses Default profile behavior)

#### Scenario: Task event published
- **WHEN** a task is created from an email
- **THEN** a `task_created` WebSocket event is published

### Requirement: Polling fallback
When the IMAP server does not support IDLE, the poller SHALL fall back to periodic polling. The poll interval SHALL be read from the email task generator's config. The minimum poll interval SHALL be 60 seconds; values below 60 SHALL be clamped to 60.

#### Scenario: Server does not support IDLE
- **WHEN** the IMAP server does not advertise IDLE in its CAPABILITY response
- **THEN** the poller uses periodic polling at the interval from the task generator config

#### Scenario: Poll interval minimum enforcement
- **WHEN** the configured poll interval is 30 seconds
- **THEN** the poller uses 60 seconds (the enforced minimum)

#### Scenario: Default poll interval
- **WHEN** no poll interval is configured in the task generator
- **THEN** the poller uses 60 seconds as the default
