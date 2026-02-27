## Purpose

Slack app_mention event handling — creating tasks from @mentions with user email resolution.

## Requirements

### Requirement: App mention event handling

The backend SHALL handle Slack `event_callback` payloads with event type `app_mention` at the existing `POST /slack/events` endpoint. The endpoint SHALL verify the Slack request signature using the existing `verify_slack_request` dependency. Upon receiving a valid `app_mention` event, the backend SHALL return HTTP 200 immediately and process the event asynchronously.

#### Scenario: Valid app_mention creates a task
- **WHEN** Slack sends an `event_callback` with event type `app_mention` and text `<@U12345> Write a blog post`
- **THEN** the endpoint returns HTTP 200, and a task is created with title `Write a blog post`, `created_by` set to the mentioning user's resolved email, category `immediate`, status `pending`, and a `slack` tag

#### Scenario: Mention with no text after bot ID
- **WHEN** Slack sends an `app_mention` event where the text is only `<@U12345>` with no additional text
- **THEN** no task is created and no confirmation message is posted (silently ignored)

#### Scenario: Mention text extraction
- **WHEN** the event text is `<@U12345> Deploy the new version to staging`
- **THEN** the bot mention prefix `<@U12345>` is stripped and the remaining text `Deploy the new version to staging` is trimmed and used as the task title

#### Scenario: URL verification still works
- **WHEN** Slack sends a `url_verification` challenge request
- **THEN** the endpoint returns the challenge value (existing behavior preserved)

### Requirement: Mention confirmation posted to channel

After creating a task from an `app_mention` event, the backend SHALL post a Block Kit confirmation message to the same channel using the Slack `chat.postMessage` API. The message SHALL include the task title, status, category, short ID, and interactive action buttons (View Status, View Output). The `channel` and `ts` from the `chat.postMessage` response SHALL be stored in the `slack_message_refs` table for later updates.

#### Scenario: Confirmation posted to source channel
- **WHEN** a task is created from an `app_mention` in channel `C12345`
- **THEN** a Block Kit confirmation message is posted to channel `C12345` via `chat.postMessage`

#### Scenario: Message reference stored
- **WHEN** `chat.postMessage` succeeds and returns `channel: C12345, ts: 1234567890.123456`
- **THEN** a `slack_message_refs` row is created linking the task ID to the channel and message timestamp

#### Scenario: chat.postMessage failure
- **WHEN** `chat.postMessage` fails (e.g., bot not in channel)
- **THEN** the error is logged but the task creation is not rolled back (task exists, just no Slack confirmation)

### Requirement: Duplicate event prevention

The backend SHALL prevent duplicate task creation from Slack event retries by tracking recently processed `event_id` values. If an `event_id` has been processed within the last 5 minutes, the event SHALL be acknowledged (HTTP 200) but not processed again.

#### Scenario: Duplicate event ignored
- **WHEN** Slack retries an `app_mention` event with the same `event_id` as a previously processed event
- **THEN** the endpoint returns HTTP 200 and does not create a duplicate task

#### Scenario: Event ID cache expiry
- **WHEN** an event with the same `event_id` arrives more than 5 minutes after the first processing
- **THEN** the event is processed again (this is acceptable; the cache is best-effort)

### Requirement: Slack message reference model

A new `slack_message_refs` table SHALL store the mapping between tasks and their Slack confirmation messages.

| Column | Type | Constraints |
|--------|------|------------|
| id | UUID | Primary key, default uuid4 |
| task_id | UUID | Foreign key → tasks.id, unique, ON DELETE CASCADE |
| channel_id | VARCHAR | NOT NULL |
| message_ts | VARCHAR | NOT NULL |
| created_at | TIMESTAMP | NOT NULL, server default now() |

#### Scenario: One ref per task
- **WHEN** a task already has a `slack_message_refs` entry and a new mention creates the same task
- **THEN** the unique constraint on `task_id` prevents duplicate entries

### Requirement: Slack API client

A lightweight `SlackClient` class in `platforms/slack/client.py` SHALL provide methods for calling the Slack Web API using `httpx`. The client SHALL support `chat.postMessage` and `chat.update` methods, both accepting a bot token and returning the API response.

#### Scenario: Post message to channel
- **WHEN** `SlackClient.post_message(token, channel, blocks)` is called
- **THEN** an HTTP POST is sent to `https://slack.com/api/chat.postMessage` with the bot token as Bearer auth

#### Scenario: Update existing message
- **WHEN** `SlackClient.update_message(token, channel, ts, blocks)` is called
- **THEN** an HTTP POST is sent to `https://slack.com/api/chat.update` with the channel, ts, and new blocks
