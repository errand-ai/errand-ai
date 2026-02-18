## Context

The Slack app H.A.L. currently supports task creation only via the `/task new` slash command. The `POST /slack/events` endpoint exists but only handles Slack URL verification. The backend already publishes task lifecycle events (`task_created`, `task_updated`, `task_deleted`) to a Valkey pub/sub channel (`task_events`), consumed by WebSocket clients in the frontend. Block Kit responses are static — once sent, they are never updated.

Key existing infrastructure:
- **Event bus**: `events.py` → `publish_event(event_type, task_data)` publishes to Valkey channel `task_events`
- **Tag system**: `_sync_tags(session, task, tag_names)` in `main.py` handles find-or-create + association
- **Slack verification**: `verify_slack_request` dependency validates HMAC-SHA256 signatures
- **Identity resolution**: `resolve_slack_email(user_id, bot_token)` with 1-hour cache
- **Block Kit builders**: `blocks.py` with `task_created_blocks()`, `task_status_blocks()`, etc.

## Goals / Non-Goals

**Goals:**
- Accept `@H.A.L.` mentions as task creation triggers, using the message text as the task title
- Automatically tag all Slack-originated tasks with a `slack` tag
- Add interactive buttons to task confirmation messages for quick status/output viewing
- Dynamically update Slack confirmation messages when task status changes
- Handle Slack interactivity payloads (button clicks)

**Non-Goals:**
- Thread-aware conversations (replying in threads) — future enhancement
- Processing mentions that aren't task creation requests (no NLP/intent detection — every mention creates a task)
- Updating messages for tasks not created from Slack
- Supporting the Slack Events API v2 Socket Mode (we use HTTP push)

## Decisions

### 1. Event handling: Extend existing `/slack/events` endpoint

Extend the existing stub to handle `event_callback` payloads with `app_mention` event type. The events endpoint already handles `url_verification`, so this is a natural extension. No new route needed.

**Event payload structure** (from Slack):
```json
{
  "type": "event_callback",
  "event": {
    "type": "app_mention",
    "text": "<@U12345> Write a blog post about Kubernetes",
    "user": "U67890",
    "channel": "C11111",
    "ts": "1234567890.123456"
  }
}
```

The handler will:
1. Strip the bot mention (`<@BOTID>`) from the text to extract the task title
2. Resolve the user's email via `resolve_slack_email`
3. Create the task with `slack` tag
4. Post a confirmation message to the channel using `chat.postMessage` (since mentions happen in channels, not as slash command responses)

### 2. Slack message reference storage: New `SlackMessageRef` model

To update Slack messages later, we need to store the `channel` and `ts` (message timestamp) that Slack returns from `chat.postMessage`. Rather than adding columns to the Task model (which would couple Task to Slack), create a separate `slack_message_refs` table:

```
slack_message_refs
  id: UUID (PK)
  task_id: UUID (FK → tasks.id, unique)
  channel_id: VARCHAR (Slack channel ID)
  message_ts: VARCHAR (Slack message timestamp)
  created_at: TIMESTAMP
```

This keeps Slack-specific data isolated. For slash command responses, we cannot get a message ref (ephemeral messages don't have a `ts`), so we'll change `/task new` to post a **non-ephemeral** response via `response_url` with `response_type: "in_channel"` — or better, use `chat.postMessage` to post a follow-up message that we control. The simpler approach: for slash commands, continue returning ephemeral responses (no update tracking), and only track mention-originated messages. This avoids changing the existing slash command behavior.

**Decision**: Only mention-originated task confirmations will be dynamically updated. Slash command confirmations remain ephemeral and static. This is simpler and doesn't break existing behavior.

### 3. Tag assignment: Extract `_add_tag` helper from `_sync_tags`

The existing `_sync_tags` replaces all tags on a task. For the Slack handler, we need to add a single tag without replacing others. Extract a lighter `_add_tag(session, task_id, tag_name)` helper that:
1. Finds or creates the tag by name
2. Inserts the association (ignoring duplicates)

This will be placed in a shared location accessible to both `main.py` and the Slack handlers.

### 4. Interactive buttons: Block Kit actions with encoded task ID

Add an `actions` block to `task_created_blocks()` with two buttons:
- "View Status" → `action_id: "task_status"`, `value: "<task_uuid>"`
- "View Output" → `action_id: "task_output"`, `value: "<task_uuid>"`

Slack sends button clicks to the **Interactivity Request URL** (`POST /slack/interactions`). This is a new endpoint that:
1. Verifies the Slack signature
2. Parses the interaction payload
3. Dispatches based on `action_id` to existing `handle_status` / `handle_output`
4. Returns a Block Kit response (replaces the original message or sends ephemeral)

### 5. Dynamic status updates: Valkey subscriber background task

A background asyncio task subscribes to the `task_events` Valkey channel. When a `task_updated` event arrives:
1. Look up `slack_message_refs` for the task ID
2. If a ref exists, call `chat.update` with the channel, ts, and updated Block Kit blocks
3. Update the status/emoji in the message to reflect the new status

This subscriber runs as part of the FastAPI application lifecycle (started in `lifespan`). It reuses the existing Valkey connection.

**Rate limiting**: Slack's `chat.update` has a rate limit of ~50 req/min per workspace. For a single-workspace deployment this is fine. No additional rate limiting needed initially.

### 6. Slack API client: httpx-based lightweight client

Rather than adding the heavy `slack_sdk` dependency, use `httpx` (already a project dependency) to call:
- `chat.postMessage` — post mention confirmation messages
- `chat.update` — update messages on status change

A small `SlackClient` class in `platforms/slack/client.py` wrapping these two calls.

### 7. Events endpoint authentication

The `/slack/events` endpoint must verify Slack request signatures just like `/slack/commands`. Reuse the existing `verify_slack_request` dependency. However, Slack Events API expects a `200 OK` response within 3 seconds — so task creation must be done asynchronously (use `asyncio.create_task` or `BackgroundTasks`) to avoid timeout.

## Risks / Trade-offs

- **3-second event response deadline**: Slack requires a 200 response within 3 seconds for events. Task creation + tag assignment + `chat.postMessage` might exceed this. Mitigation: Return 200 immediately, process asynchronously via `BackgroundTasks`.
- **Ephemeral vs. in_channel for slash commands**: Keeping slash command responses ephemeral means they won't get interactive buttons that update. This is acceptable — the buttons still work for status/output lookups, they just won't auto-update.
- **Duplicate event delivery**: Slack may retry event delivery if we don't respond quickly enough. Mitigation: Use the `event_id` field for idempotency — cache recently processed event IDs.
- **Bot mention regex**: The mention format `<@BOTID>` is stable, but we need to handle edge cases: mention at start, middle, or end of text; multiple mentions; mention with no text after it.
- **Message ref cleanup**: `slack_message_refs` rows accumulate. Consider a periodic cleanup for tasks older than N days. Not critical for initial implementation.
