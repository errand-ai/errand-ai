## ADDED Requirements

### Requirement: slack_message MCP tool
The errand MCP server SHALL expose a tool named `slack_message` to the task-runner. The tool SHALL accept `target` (string), `text` (string), and optional `blocks` (list). The tool SHALL post a new Slack message to the resolved target via `chat.postMessage` using the workspace bot token loaded server-side. The tool SHALL return a JSON object containing `ok` (boolean), `channel` (string), `ts` (string), and an `error` field (string) when `ok` is false. The bot token SHALL never be transmitted to the task-runner.

#### Scenario: Post to a channel by name
- **WHEN** the task-runner calls `slack_message(target="#ai-agent", text="task complete")`
- **THEN** the server resolves `#ai-agent` to a channel ID, posts via `chat.postMessage`, and returns `{ok: true, channel: "C…", ts: "…"}`

#### Scenario: Post to a channel by ID
- **WHEN** the task-runner calls `slack_message(target="C0123ABCD", text="hello")`
- **THEN** the server posts to channel `C0123ABCD` without name resolution and returns `{ok: true, channel: "C0123ABCD", ts: "…"}`

#### Scenario: Direct-message a user by username
- **WHEN** the task-runner calls `slack_message(target="@rob", text="reminder")`
- **THEN** the server resolves `@rob` to a user ID and posts via `chat.postMessage` with the user ID as `channel`, returning `{ok: true, channel: "D…" or "U…", ts: "…"}`

#### Scenario: Direct-message a user by email
- **WHEN** the task-runner calls `slack_message(target="rob@example.com", text="hi")`
- **THEN** the server resolves the email via `users.lookupByEmail` and DMs the resolved user

#### Scenario: Block Kit payload
- **WHEN** the task-runner calls `slack_message(target="#ai-agent", text="fallback", blocks=[{...}])`
- **THEN** the server sends the supplied `blocks` array via `chat.postMessage` with `text` used as the notification fallback

#### Scenario: Bot token never leaves the server
- **WHEN** any task-runner inspects its environment, MCP request payload, or returned tool output
- **THEN** the Slack bot token is not present anywhere in those surfaces

### Requirement: slack_reply MCP tool
The errand MCP server SHALL expose a tool named `slack_reply` to the task-runner. The tool SHALL accept `channel` (string), `thread_ts` (string), `text` (string), and optional `blocks` (list). The tool SHALL post the message as a reply in the specified thread via `chat.postMessage` with `thread_ts` set. The tool SHALL return the same shape as `slack_message`.

#### Scenario: Reply in a thread the runner started
- **WHEN** the task-runner calls `slack_message(target="#ai-agent", text="part 1")` and receives `{ok: true, channel: "C…", ts: "T1"}`, then calls `slack_reply(channel="C…", thread_ts="T1", text="part 2")`
- **THEN** the second message is posted as a threaded reply to the first and returns `{ok: true, channel: "C…", ts: "T2"}`

#### Scenario: Reply to an arbitrary thread
- **WHEN** the task-runner is given a `channel` and `thread_ts` (e.g. by a previous human message in the thread) and calls `slack_reply` with them
- **THEN** the server posts a threaded reply regardless of who originated the thread

#### Scenario: Allowlist applies to channel
- **WHEN** the workspace allowlist is non-empty and the supplied `channel` is not in it
- **THEN** `slack_reply` returns `{ok: false, error: "channel not in slack_outbound_allowlist"}` and no Slack API call is made

### Requirement: Target resolution
The server SHALL resolve `target` strings using the following precedence:
1. Strings matching `^[CDG][A-Z0-9]{8,}$` are treated as conversation IDs.
2. Strings matching `^U[A-Z0-9]{8,}$` are treated as user IDs.
3. Strings containing `@` and matching an email pattern are resolved via Slack `users.lookupByEmail`.
4. Strings starting with `#` (or with the prefix stripped) are resolved as channel names via `conversations.list`.
5. Strings starting with `@` (or with the prefix stripped) are resolved as usernames via `users.list`.
6. Strings without a prefix that match BOTH a channel and a username SHALL return an ambiguity error.

Resolved name→ID mappings SHALL be cached in-memory per resolution kind with a 1-hour TTL.

#### Scenario: ID passes through unchanged
- **WHEN** `target="C0123ABCD"`
- **THEN** the resolver returns `("channel", "C0123ABCD")` without calling Slack

#### Scenario: Email resolves to user
- **WHEN** `target="rob@example.com"` and Slack returns user `U999`
- **THEN** the resolver returns `("user", "U999")` and caches the mapping for 1 hour

#### Scenario: Cached lookup
- **WHEN** the same channel name is resolved twice within 1 hour
- **THEN** only one Slack API call is made; the second returns from cache

#### Scenario: Ambiguous bare name
- **WHEN** `target="ai-agent"` matches both a channel `#ai-agent` and a user `@ai-agent`
- **THEN** the tool returns `{ok: false, error: "ambiguous target ..."}`

#### Scenario: Stale cache entry
- **WHEN** a cached channel name resolves to an ID that Slack now reports as `channel_not_found`
- **THEN** the server SHALL evict the stale cache entry and retry resolution once

### Requirement: Workspace allowlist enforcement
The server SHALL check every outbound call against the `slack_outbound_allowlist` setting. The setting is a list of identifiers in any accepted target form. The check SHALL use resolved IDs on both sides. An empty or unset list SHALL be interpreted as "unrestricted within the workspace" — every reachable channel and user is allowed.

#### Scenario: Empty allowlist allows all
- **WHEN** `slack_outbound_allowlist` is unset or `[]` and the runner posts to any channel or user
- **THEN** the post proceeds without an allowlist rejection

#### Scenario: Non-empty allowlist allows listed channel
- **WHEN** `slack_outbound_allowlist` is `["#ai-agent", "@rob"]` and the runner posts to `#ai-agent`
- **THEN** the post proceeds

#### Scenario: Non-empty allowlist rejects unlisted target
- **WHEN** `slack_outbound_allowlist` is `["#ai-agent"]` and the runner posts to `#general`
- **THEN** the tool returns `{ok: false, error: "target not in slack_outbound_allowlist"}` and no Slack API call is made

#### Scenario: Allowlist authored with names, target supplied with ID
- **WHEN** `slack_outbound_allowlist` is `["#ai-agent"]` (resolves to `C0123ABCD`) and the runner posts to `C0123ABCD`
- **THEN** the post proceeds because resolved IDs match

### Requirement: Auto-join public channels
When `chat.postMessage` returns `not_in_channel` for a public channel, the server SHALL attempt `conversations.join` on that channel and retry the post once. For private channels and DMs, the server SHALL NOT attempt to join — the original error SHALL be surfaced to the caller.

#### Scenario: Auto-join succeeds
- **WHEN** the bot is not in public channel `#ai-agent` and the runner calls `slack_message(target="#ai-agent", ...)`
- **THEN** the server joins the channel and the message posts on retry, returning `{ok: true, ...}`

#### Scenario: Auto-join fails
- **WHEN** the bot lacks `channels:join` scope and `conversations.join` fails
- **THEN** the tool returns `{ok: false, error: "not_in_channel; auto-join failed: <reason>"}`

#### Scenario: Private channel requires invite
- **WHEN** the bot is not a member of private channel `Cxxxx` and posts to it
- **THEN** the server does NOT attempt `conversations.join` and returns `{ok: false, error: "not_in_channel"}` directly

### Requirement: Decoupling from task origin
The `slack_message` and `slack_reply` tools SHALL operate identically regardless of whether the originating task was triggered from Slack, the kanban UI, the API, a schedule, or any other entry point. No origin context (originating channel, thread, or user) SHALL be implicit in the tool's behavior; all targets are explicit arguments.

#### Scenario: Kanban-originated task posts to Slack
- **WHEN** a task created via the kanban UI calls `slack_message(target="#ai-agent", text="…")`
- **THEN** the message is posted exactly as if the task had originated in Slack

#### Scenario: Slack-originated task posts to a different channel
- **WHEN** a task triggered from `#help` calls `slack_message(target="#announcements", text="…")`
- **THEN** the message is posted to `#announcements`, not to `#help`, with no implicit cross-posting to the origin channel

### Requirement: Outbound audit logging
The server SHALL log every outbound Slack call at info level. Each log entry SHALL include the `task_id`, the resolved target ID, `thread_ts` when applicable, the returned message `ts` on success, and the Slack error code on failure. No additional persistence (e.g. database table) SHALL be required by this change.

#### Scenario: Successful post is logged
- **WHEN** `slack_message` posts to channel `C123` and Slack returns `ts="1700000000.000100"`
- **THEN** an info-level log entry is emitted containing `task_id`, `target=C123`, `ts=1700000000.000100`

#### Scenario: Failed post is logged
- **WHEN** `slack_message` is rejected by Slack with `error="channel_not_found"`
- **THEN** an info-level log entry is emitted containing `task_id`, `target`, and `error=channel_not_found`

### Requirement: Rate limit handling
When Slack returns HTTP 429 for any outbound call, the server SHALL NOT retry. The tool SHALL return `{ok: false, error: "rate_limited; retry after <N> seconds"}` where `<N>` is the value of the `Retry-After` response header.

#### Scenario: Rate limit surfaced to runner
- **WHEN** Slack responds with 429 and `Retry-After: 30`
- **THEN** the tool returns `{ok: false, error: "rate_limited; retry after 30 seconds"}` and the LLM decides whether to wait or proceed
