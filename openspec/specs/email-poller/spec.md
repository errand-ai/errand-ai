## Purpose

Background email poller that monitors a dedicated mailbox using IMAP IDLE (with polling fallback), creates tasks from unread emails, and marks them as read.

## ADDED Requirements

### Requirement: Email poller background task

The system SHALL run an email poller as an `asyncio.create_task()` in the main server lifespan. The poller SHALL load email platform credentials on each cycle. If no credentials are configured, the poller SHALL sleep and retry. The poller SHALL run continuously until the application shuts down.

#### Scenario: Poller starts with application

- **WHEN** the FastAPI application starts and email platform credentials are configured
- **THEN** the email poller begins monitoring the configured mailbox

#### Scenario: Poller waits when unconfigured

- **WHEN** the FastAPI application starts and no email platform credentials are configured
- **THEN** the email poller sleeps and periodically checks for credentials

#### Scenario: Poller stops on shutdown

- **WHEN** the FastAPI application receives a shutdown signal
- **THEN** the email poller cancels cleanly and closes any IMAP connections

### Requirement: IMAP IDLE support

The poller SHALL check the IMAP server's CAPABILITY response for IDLE support. When IDLE is supported, the poller SHALL enter IMAP IDLE mode and wait for server notifications of new messages. The poller SHALL exit IDLE on notification or after a configurable timeout (to handle servers that drop IDLE connections). After exiting IDLE, the poller SHALL process new messages and re-enter IDLE.

#### Scenario: Server supports IDLE

- **WHEN** the IMAP server advertises IDLE in its CAPABILITY response
- **THEN** the poller uses IDLE mode and receives push notifications of new mail

#### Scenario: IDLE timeout re-entry

- **WHEN** the IDLE connection has been active for the timeout period without notifications
- **THEN** the poller exits IDLE, performs a safety check for UNSEEN messages, and re-enters IDLE

#### Scenario: IDLE connection dropped

- **WHEN** the IDLE connection is dropped by the server or network
- **THEN** the poller detects the disconnection, reconnects, and resumes IDLE

### Requirement: Polling fallback

When the IMAP server does not support IDLE, the poller SHALL fall back to periodic polling. The poll interval SHALL be configurable via the `poll_interval` credential field. The minimum poll interval SHALL be 60 seconds; values below 60 SHALL be clamped to 60.

#### Scenario: Server does not support IDLE

- **WHEN** the IMAP server does not advertise IDLE in its CAPABILITY response
- **THEN** the poller uses periodic polling at the configured interval

#### Scenario: Poll interval minimum enforcement

- **WHEN** the configured poll interval is 30 seconds
- **THEN** the poller uses 60 seconds (the enforced minimum)

#### Scenario: Default poll interval

- **WHEN** no poll interval is configured
- **THEN** the poller uses 60 seconds as the default

### Requirement: Unread message processing

On each poll cycle (or IDLE notification), the poller SHALL fetch all messages with the `\Unseen` flag from the INBOX folder. For each unread message, the poller SHALL extract: the IMAP message UID, sender (From), recipients (To, Cc), subject, date, and body.

#### Scenario: Fetch unread messages

- **WHEN** the poller checks the INBOX and there are 3 unread messages
- **THEN** all 3 messages are fetched with their metadata and body content

#### Scenario: No unread messages

- **WHEN** the poller checks the INBOX and there are no unread messages
- **THEN** no tasks are created and the poller continues to the next cycle

### Requirement: Email body conversion

The poller SHALL convert email bodies to markdown. For multipart messages, the poller SHALL prefer the `text/html` part and convert it to markdown using `html2text`. If no HTML part exists, the poller SHALL use the `text/plain` part. The markdown body SHALL be truncated to 50,000 characters.

#### Scenario: HTML email conversion

- **WHEN** a multipart email has both `text/html` and `text/plain` parts
- **THEN** the `text/html` part is converted to markdown

#### Scenario: Plain text email

- **WHEN** an email has only a `text/plain` part
- **THEN** the plain text is used directly as the task description

#### Scenario: Large email truncation

- **WHEN** an email body converts to markdown exceeding 50,000 characters
- **THEN** the body is truncated to 50,000 characters

### Requirement: Task creation from email

For each unread message, the poller SHALL create a task with: `title` derived from the email subject, `description` containing email metadata (from, to, date, subject) and the markdown body, `profile_id` set to the configured email profile, `created_by` set to `"email_poller"`, and `status` set to `"pending"`. The poller SHALL publish a `task_created` WebSocket event for each created task.

#### Scenario: Task created from email

- **WHEN** a new unread email arrives with subject "Invoice #1234 from Acme Corp"
- **THEN** a task is created with title "Invoice #1234 from Acme Corp", description containing email metadata and markdown body, the configured email profile, and `created_by="email_poller"`

#### Scenario: Task event published

- **WHEN** a task is created from an email
- **THEN** a `task_created` WebSocket event is published

### Requirement: Duplicate detection

The poller SHALL store the IMAP message UID in the task description or metadata. Before creating a task for a message, the poller SHALL check if a task with the same IMAP UID and `created_by="email_poller"` already exists. If a duplicate is found, the poller SHALL skip task creation for that message.

#### Scenario: Duplicate message skipped

- **WHEN** the poller encounters a message whose UID already has a corresponding task
- **THEN** no new task is created for that message

#### Scenario: First encounter creates task

- **WHEN** the poller encounters a message whose UID does not have a corresponding task
- **THEN** a new task is created

### Requirement: Mark as read after task creation

After successfully creating a task for a message, the poller SHALL add the `\Seen` flag to the message on the IMAP server. This SHALL happen immediately after task creation, not after agent processing.

#### Scenario: Message marked as read

- **WHEN** a task is successfully created from an unread email
- **THEN** the email is marked as `\Seen` on the IMAP server

#### Scenario: Task creation fails

- **WHEN** task creation fails for an unread email
- **THEN** the email remains unread and will be retried on the next cycle

### Requirement: Connection error resilience

The poller SHALL handle IMAP connection errors gracefully. On connection failure, the poller SHALL log the error, wait with exponential backoff (starting at 5 seconds, up to 5 minutes), and attempt to reconnect.

#### Scenario: Connection lost during polling

- **WHEN** the IMAP connection is lost during a poll cycle
- **THEN** the poller logs the error, waits, and reconnects

#### Scenario: Repeated connection failures

- **WHEN** multiple consecutive connection attempts fail
- **THEN** the backoff interval increases up to the maximum of 5 minutes
