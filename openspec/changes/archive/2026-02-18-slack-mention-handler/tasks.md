## 1. Database & Models

- [x] 1.1 Create `SlackMessageRef` SQLAlchemy model in `backend/models.py` with columns: id (UUID PK), task_id (UUID FK unique), channel_id (VARCHAR), message_ts (VARCHAR), created_at (TIMESTAMP)
- [x] 1.2 Create Alembic migration for `slack_message_refs` table
- [x] 1.3 Extract `add_tag(session, task_id, tag_name)` helper from `_sync_tags` into a shared module (e.g. `backend/tags.py`) that finds-or-creates a tag and inserts the association

## 2. Slack API Client

- [x] 2.1 Create `backend/platforms/slack/client.py` with `SlackClient` class providing `post_message(token, channel, blocks)` and `update_message(token, channel, ts, blocks)` methods using httpx
- [x] 2.2 Write tests for `SlackClient` (mock httpx calls, verify request format and auth headers)

## 3. Block Kit Interactive Buttons

- [x] 3.1 Add `actions` block to `task_created_blocks()` in `blocks.py` with "View Status" (`action_id: task_status`) and "View Output" (`action_id: task_output`) buttons, both carrying the full task UUID as `value`
- [x] 3.2 Create `task_updated_blocks(task)` helper in `blocks.py` that returns the same structure as `task_created_blocks` (for use when updating messages via `chat.update`)
- [x] 3.3 Update existing `task_created_blocks` tests and add tests for the new action buttons

## 4. Slack Tag on Task Creation

- [x] 4.1 Update `handle_new` in `handlers.py` to add a `slack` tag to the created task using the `add_tag` helper
- [x] 4.2 Write tests verifying `/task new` creates tasks with a `slack` tag

## 5. App Mention Event Handler

- [x] 5.1 Extend `slack_events` in `routes.py` to handle `event_callback` with `app_mention` event type: verify signature, return 200 immediately, process asynchronously via `BackgroundTasks`
- [x] 5.2 Implement mention handler: strip bot mention from text, resolve user email, create task with `slack` tag, post confirmation to channel via `SlackClient.post_message`, store `SlackMessageRef`
- [x] 5.3 Add duplicate event prevention using an in-memory TTL cache keyed by `event_id` (5-minute expiry)
- [x] 5.4 Write tests for mention event handling (task creation, tag assignment, bot mention stripping, empty text handling, duplicate prevention)

## 6. Interactions Endpoint

- [x] 6.1 Add `POST /slack/interactions` route in `routes.py` that verifies signature, parses the `payload` JSON from form data, and dispatches `block_actions` to `handle_status` / `handle_output` based on `action_id`
- [x] 6.2 Write tests for the interactions endpoint (button click dispatch, unknown action handling, signature verification)

## 7. Task Status Update Subscriber

- [x] 7.1 Create `backend/platforms/slack/status_updater.py` with a Valkey subscriber that listens on `task_events` channel for `task_updated` events, looks up `SlackMessageRef`, and calls `SlackClient.update_message` with updated blocks
- [x] 7.2 Register the subscriber as a background task in FastAPI `lifespan` (start on startup, cancel on shutdown)
- [x] 7.3 Write tests for the status updater (event processing, message ref lookup, chat.update call, missing ref skip, error handling)

## 8. Integration & Documentation

- [x] 8.1 Add `app_mentions:read` to the Slack app scope documentation / setup notes and verify the events endpoint URL is configured in the Slack app
- [x] 8.2 Add `chat:write` bot scope if not already documented
- [x] 8.3 Add interactivity request URL (`/slack/interactions`) to Slack app configuration documentation
