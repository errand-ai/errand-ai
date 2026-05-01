## Context

The errand task-runner runs in an isolated container per task. It already receives Slack input via cloud-relayed slash commands and @-mentions, and the server already updates a per-task Slack confirmation card via the `slack_status_updater` pubsub subscriber. There is currently no path for the runner to *originate* a Slack message — it can only return its result via `submit_result`, where the user sees it in the kanban UI (and via the existing status card update if the task originated from Slack).

The runner already speaks MCP to the errand backend's `mcp_server.py`, where tools like `new_task` and `task_status` live. Tool catalog access is lazy: tools not in the hot list appear in the `<available_mcp_tools>` catalog and must be enabled via `discover_tools` before use. Slack credentials (bot token) are stored encrypted in the credentials table and loaded server-side via `load_credentials_fn("slack", session)`.

## Goals / Non-Goals

**Goals:**
- Give task-runner two MCP tools (`slack_message`, `slack_reply`) that post to Slack via the errand backend, with the bot token never leaving the server.
- Allow the LLM to address channels and users by human-friendly names or IDs.
- Enforce a workspace-scoped allowlist with a sensible default (empty = unrestricted within the workspace).
- Keep the tools fully decoupled from how the task was triggered.

**Non-Goals:**
- Persisting an outbound-message audit table (Slack itself is the record; server logs are sufficient).
- Editing or deleting messages the task-runner has posted (`chat.update`, `chat.delete`) — out of scope; can be added later if needed.
- File uploads, reactions, scheduled messages, or DMs to multi-person groups.
- Any change to how the existing Slack confirmation card or status updater behaves.
- Cross-workspace messaging — single-workspace assumption matches the rest of the Slack integration.

## Decisions

### Decision 1: MCP tools on the existing errand MCP server (server-mediated)

**Choice:** Add `slack_message` and `slack_reply` as tools on `errand/mcp_server.py`. The runner calls them like any other MCP tool; the server holds the bot token and calls Slack.

**Why:** The bot token has broad scope; injecting it into the runner's env (the `gws` pattern) gives the LLM and any shell tool the ability to post anywhere as the bot. Server-mediated keeps the credential out of the sandbox, makes allowlist enforcement and audit logging trivial, and matches the existing pattern for tools that need server state (e.g. `new_task`).

**Alternatives considered:**
- *Inject `SLACK_BOT_TOKEN` env var + ship a `slack` CLI like `gws`* — simpler, but exposes the token to the sandbox. Rejected.
- *Direct HTTP callback to errand server using `RESULT_CALLBACK_TOKEN`* — works, but adds a new endpoint surface for something the existing MCP transport already covers. Rejected.

### Decision 2: Tool surface and signatures

```
slack_message(target: str, text: str, blocks: list | None = None)
  → {ok: bool, channel: str, ts: str, error?: str}

slack_reply(channel: str, thread_ts: str, text: str, blocks: list | None = None)
  → {ok: bool, channel: str, ts: str, error?: str}
```

- `target` accepts: channel ID (`C12345`), channel name (`#ai-agent` or `ai-agent`), user ID (`U12345`), username (`@rob` or `rob`), or email (`rob@example.com`).
- `text` is required; if `blocks` is also provided, `blocks` is sent and `text` is used as the fallback notification text (matching Slack's own contract).
- `slack_reply` requires both `channel` and `thread_ts` because Slack's `chat.postMessage` does. The runner gets both from the return value of an earlier `slack_message` (or `slack_reply`) call.

**Why two tools, not one:** Discoverability and lower mis-use risk. The LLM picks the verb that matches its intent rather than juggling an optional `thread_ts` parameter on a single `slack_send`.

### Decision 3: Target resolution

Server-side resolver:
1. If the input matches `^[CDG][A-Z0-9]{8,}$` → treat as channel/conversation ID.
2. Else if `^U[A-Z0-9]{8,}$` → treat as user ID.
3. Else if contains `@` → treat as email, resolve via `users.lookupByEmail`.
4. Else strip leading `#` or `@` and try channel-name resolution (`conversations.list`, paginated, cached) then username resolution (`users.list`, cached).

Cache: in-memory dict per resolution kind, 1-hour TTL, mirroring the existing `resolve_slack_email` pattern. On ambiguity (name matches both a channel and a user), prefer the explicit prefix; if no prefix, return an error asking the caller to disambiguate.

**Why:** Slack IDs are robust but unfriendly to LLMs. Names are friendly but mutable. Accepting both keeps the tool ergonomic and lets the allowlist itself be authored with names while resolved to IDs internally.

### Decision 4: Allowlist semantics

Setting key: `slack_outbound_allowlist`. Type: list of strings. Each entry is a channel/user identifier in any of the accepted forms (resolved to IDs server-side at check time, with the same cache).

- Empty list (`[]` or unset) → unrestricted within the workspace. Any channel the bot is in (or can join) and any user in the workspace is reachable.
- Non-empty list → strict allowlist. Targets resolved to IDs and compared against resolved allowlist IDs.
- Allowlist applies to both `slack_message` and `slack_reply`. For `slack_reply`, the `channel` is checked.

**Why empty = unrestricted:** Matches the user's stated intent and keeps the default low-friction for single-team installations. Workspaces that want stricter controls add entries explicitly.

### Decision 5: Auto-join public channels

When `chat.postMessage` to a public channel returns `not_in_channel`, server attempts `conversations.join` and retries once. For private channels and DMs, no auto-join — return the Slack error verbatim (`channel_not_found`, `not_in_channel`, or similar) so the user invites the bot manually.

**Why:** Avoids the worst foot-gun (the bot silently failing on a channel it could trivially join) without surprising users in private contexts where joining requires explicit consent.

### Decision 6: Text vs Block Kit

Server wraps a bare `text` value in a single `section` block with `mrkdwn` before calling `chat.postMessage` so all messages flow through the same blocks code path. If `blocks` is supplied, it is used directly; `text` is still sent as the fallback notification text.

**Why:** Lets the LLM produce the simplest possible payload by default, while not blocking richer Block Kit output when the task warrants it.

### Decision 7: Return shape and follow-on threading

Both tools return `{ok, channel, ts, error?}`. The `ts` is the canonical handle for follow-on replies; the LLM holds it across turns. No server-side "last posted" state — all threading is explicit.

**Why:** Keeps the server stateless w.r.t. the runner and makes the contract obvious. If we later want auto-thread-to-self, we can layer it on without breaking the explicit form.

### Decision 8: Audit via logs only

Log every outbound call at info level: `task_id`, `target` (resolved ID), `thread_ts` if any, returned `ts`, and any error. No new database table for v1.

**Why:** Slack itself is the durable record. Adding a table is cheap later if we want a UI surface.

## Risks / Trade-offs

- **[Bot scope creep]** Outbound messaging needs `chat:write`, likely `chat:write.public`, `im:write`, `channels:read`, `groups:read`, possibly `channels:join`. → Mitigation: audit current scopes during implementation; add minimum needed; document in install instructions.
- **[Empty allowlist is wide-open by default]** A misconfigured task could spam channels. → Mitigation: clear documentation; future enhancement could log a warning when posting to a channel not in the allowlist when allowlist is empty; rate-limiting if abuse appears.
- **[Name resolution drift]** Channel/username caches go stale across renames. → Mitigation: 1-hour TTL; on `channel_not_found` clear the cached entry and retry once.
- **[Slack rate limits]** `chat.postMessage` is Tier 4 (1+ per second per channel). A chatty task could be throttled. → Mitigation: surface 429 responses with `Retry-After` directly in the tool's `error` field; don't retry server-side.
- **[Bot can't reach user via DM]** First-time DMs to users who haven't installed the app may fail. → Mitigation: surface the error; document the requirement.
- **[Catalog discoverability]** Lazy-loaded MCP tools require `discover_tools` first; the LLM may not realize they exist without prompting. → Mitigation: include a brief mention of the outbound tools in the system prompt when Slack credentials are present.

## Migration Plan

No data migration required. Rollout:

1. Ship the new SlackClient methods, resolver, allowlist enforcement, and MCP tools behind no feature flag — they are net-new tools and inert until the LLM calls them.
2. Verify scopes on the existing bot installation; if any are missing, document the re-install requirement in release notes.
3. After deploy, optionally seed the `slack_outbound_allowlist` setting in any workspace that wants strict mode; leave empty otherwise.

Rollback: revert the deploy. No persistent state is created by this change.

## Open Questions

- Should we add a per-task or per-profile cap on how many outbound Slack messages a single task can send (anti-spam)? Default to none for v1; revisit if we see abuse.
- Should the system prompt automatically mention the Slack tools when Slack is connected, or rely on the standard MCP catalog discovery flow? Lean toward catalog-only for v1 and re-evaluate after observing usage.
