## Purpose

Background subscriber that updates Slack confirmation messages when task status changes via pub/sub events.

## Requirements

### Requirement: Task status change subscriber

A background asyncio task SHALL subscribe to the `task_events` Valkey pub/sub channel and listen for `task_updated` events. When a `task_updated` event is received for a task that has a `slack_message_refs` entry, the subscriber SHALL update the Slack confirmation message to reflect the new task status.

#### Scenario: Task status changes from pending to running
- **WHEN** a `task_updated` event is published for task `abc123` with status `running`, and task `abc123` has a `slack_message_refs` entry for channel `C12345` / ts `1234567890.123`
- **THEN** the Slack message at `C12345` / `1234567890.123` is updated via `chat.update` with the new status emoji and text

#### Scenario: Task completes
- **WHEN** a `task_updated` event is published for task `abc123` with status `completed`
- **THEN** the Slack message is updated to show `:white_check_mark: completed` status

#### Scenario: No message ref for task
- **WHEN** a `task_updated` event is published for a task that has no `slack_message_refs` entry
- **THEN** no Slack API call is made (silently skipped)

#### Scenario: chat.update fails
- **WHEN** `chat.update` fails (e.g., message deleted, channel archived)
- **THEN** the error is logged and the message ref is optionally deleted to prevent future retries

### Requirement: Status update subscriber lifecycle

The Valkey subscriber SHALL be started during FastAPI application startup (in the `lifespan` context manager) and cancelled during shutdown. The subscriber SHALL reconnect if the Valkey connection is lost.

#### Scenario: Subscriber starts with application
- **WHEN** the FastAPI application starts
- **THEN** the Slack status update subscriber begins listening on the `task_events` channel

#### Scenario: Subscriber stops on shutdown
- **WHEN** the FastAPI application shuts down
- **THEN** the subscriber task is cancelled and resources are cleaned up

#### Scenario: Valkey connection lost
- **WHEN** the Valkey connection drops while the subscriber is running
- **THEN** the subscriber logs the error and attempts to reconnect after a brief delay

### Requirement: Updated message format

When a Slack confirmation message is updated due to a status change, the message SHALL retain the original task information (title, category, ID) and update only the status field with the new status emoji and text. The interactive buttons (View Status, View Output) SHALL remain in the updated message.

#### Scenario: Message preserves structure after update
- **WHEN** a task confirmation message is updated from `pending` to `running`
- **THEN** the updated message contains the same header, title, category, and ID fields, with status changed to `:gear: running`, and action buttons still present
