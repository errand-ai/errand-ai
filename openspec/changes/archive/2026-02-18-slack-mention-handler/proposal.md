## Why

The Slack app H.A.L. currently only accepts tasks via the `/task` slash command. Users should also be able to @mention H.A.L. in any message to create a task, which is a more natural interaction pattern — especially in threaded conversations. Additionally, Slack-originated tasks lack traceability (no tag) and the confirmation messages are static with no way to quickly check task progress without typing another command.

## What Changes

- Add an `app_mention` event handler so that `@H.A.L.` messages are received by the backend and processed as new tasks
- Automatically add a `slack` tag to every task created from Slack (both slash commands and mentions)
- Extend the Block Kit confirmation message to include interactive buttons: "View Status" and "View Output"
- Dynamically update the confirmation message as task status changes (pending → running → completed) using Slack's `chat.update` API
- Subscribe to internal task status-change events to trigger Slack message updates

## Capabilities

### New Capabilities
- `slack-mention-events`: Handles `app_mention` events from Slack, extracts the message text, and creates a task via the existing task-creation flow
- `slack-interactive-messages`: Adds interactive Block Kit buttons (View Status, View Output) to confirmation messages and handles button interactions via the Slack interactivity endpoint
- `slack-task-status-updates`: Subscribes to task lifecycle events and pushes status updates back to Slack by editing the original confirmation message

### Modified Capabilities
- `slack-commands`: Add automatic `slack` tag to tasks created via `/task new`; update `task_created_blocks` to include interactive buttons

## Impact

- **Backend routes**: New `/slack/events` handler for `app_mention` (extends existing stub), new `/slack/interactions` endpoint for button payloads
- **Backend blocks.py**: Updated `task_created_blocks()` with action buttons; new helper for status-update messages
- **Backend handlers.py**: Task creation adds `slack` tag; stores Slack `channel` + `ts` (message timestamp) for later updates
- **Task model**: May need a metadata/source field or use existing tag system to track Slack message references
- **Slack app config**: Requires `app_mentions:read` event subscription scope, `chat:write` bot scope for posting/updating messages, and interactivity request URL
- **Event integration**: Consumes task status-change events from the existing structured-task-events system (Valkey pub/sub)
- **Database**: Migration for storing Slack message references (channel_id + message_ts per task)
