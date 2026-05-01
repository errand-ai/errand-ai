## Why

Today the task-runner can receive Slack input (slash commands, @-mentions) and the server can update the originating Slack confirmation card with task status, but the task-runner itself cannot send arbitrary messages back to Slack. Tasks that produce useful output (a summary, a reminder, an alert) have no way to deliver it into a Slack channel or DM unless the user happens to have triggered the task from Slack and reads the status card. Exposing first-class outbound messaging tools to the task-runner makes Slack a real output channel, not just an input/status surface.

## What Changes

- Add two MCP tools on the existing errand MCP server:
  - `slack_message(target, text, blocks?)` — post a new message to a channel or DM a user.
  - `slack_reply(channel, thread_ts, text, blocks?)` — reply in an existing thread.
- Resolve human-friendly targets server-side: channel name (`#ai-agent`), channel ID (`C12345`), username (`@rob`), user ID (`U12345`), or email. Cache name→ID lookups in-memory.
- Add a workspace-scoped allowlist setting (`slack_outbound_allowlist`) of channel/user identifiers. Empty list means anyone in the workspace is reachable; non-empty list restricts targets to the listed entries.
- Auto-join public channels on first post when the bot is not already a member; surface a clear error for private channels and DMs requiring an invite.
- Extend `SlackClient` to accept either `text` (Slack mrkdwn, wrapped server-side into a section block) or explicit `blocks`, and to support `thread_ts` on `chat.postMessage`.
- Both tools return `{ok, channel, ts, error?}`. The returned `ts` enables follow-on `slack_reply` calls within the same task.
- Audit each outbound call at info-level (task_id, target, ts) — no new database table.
- The tools are decoupled from task origin: any task can post anywhere it is permitted to, regardless of how the task was triggered.

## Capabilities

### New Capabilities
- `slack-outbound-messaging`: MCP tools `slack_message` and `slack_reply` exposed to the task-runner, target resolution, allowlist enforcement, auto-join behavior, return contract.

### Modified Capabilities
- `slack-webhook-security`: no change to verification — outbound is server-initiated, not webhook-driven. (Listed only to confirm we are NOT touching it.)

(No existing spec covers the SlackClient surface or task-runner MCP tool catalog as requirements, so no delta specs are required for them.)

## Impact

- **Code**:
  - `errand/platforms/slack/client.py` — widen `post_message` to accept text or blocks and an optional `thread_ts`.
  - `errand/platforms/slack/identity.py` — add channel-name and username resolution alongside the existing email resolution, with caching.
  - `errand/mcp_server.py` — register two new MCP tools backed by the SlackClient and the resolver.
  - `errand/models.py` / settings — register the `slack_outbound_allowlist` setting key (no migration needed if stored under the existing settings table).
  - `task-runner/main.py` — no code changes; tools are discovered through the existing MCP catalog / `discover_tools` path.
- **Slack scopes**: bot manifest may need `chat:write.public`, `im:write`, `channels:read`, `groups:read`, and `channels:join` if not already present. To be audited during implementation.
- **Tests**: new unit tests for the resolver, allowlist enforcement, and the two MCP tool handlers.
- **Docs**: update `CLAUDE.md` Slack section to mention the outbound tools and allowlist setting.
- **No DB migration required** unless we decide to persist outbound audit (out of scope for this change).
