## 1. SlackClient & resolver groundwork

- [x] 1.1 Widen `SlackClient.post_message` in `errand/platforms/slack/client.py` to accept `text: str | None = None`, `blocks: list | None = None`, and `thread_ts: str | None = None`; build the request body to include `text` (always, for fallback notifications), `blocks` (when supplied), and `thread_ts` (when supplied)
- [x] 1.2 Add a helper that wraps a bare `text` value into a single `section` block with `mrkdwn` so the call path through SlackClient is uniform
- [x] 1.3 Verify existing callers (`status_updater.py`, `routes.py`) keep working unchanged after the signature widening; add tests if needed
- [x] 1.4 Add `resolve_slack_target(token, target) -> tuple[Literal["channel","user"], str]` in `errand/platforms/slack/identity.py` implementing the precedence order from the spec (ID → email → `#channel` → `@user` → bare ambiguous)
- [x] 1.5 Add a per-kind in-memory cache (`_channel_name_cache`, `_user_name_cache`, `_email_cache`) with 1-hour TTL, mirroring the existing `resolve_slack_email` cache shape
- [x] 1.6 Add cache eviction on `channel_not_found` so a subsequent retry can re-resolve a renamed channel
- [x] 1.7 Unit tests covering ID pass-through, email lookup, channel-name resolution, username resolution, ambiguity error, and cache hit/miss/eviction

## 2. Allowlist enforcement

- [x] 2.1 Define the `slack_outbound_allowlist` setting key (string list); document default behavior (empty = unrestricted) in code comments
- [x] 2.2 Add `check_outbound_allowlist(token, resolved_id, allowlist) -> bool` that resolves every entry in the allowlist (using the cache from §1) and compares resolved IDs
- [x] 2.3 Unit tests: empty allowlist allows all; non-empty allowlist allows listed entry by name and by ID; non-empty allowlist rejects non-listed; allowlist authored with names matches a target supplied as ID

## 3. Auto-join behavior

- [x] 3.1 Add `SlackClient.join_channel(token, channel_id)` wrapping `conversations.join`
- [x] 3.2 In the post-message path, on `not_in_channel` for a channel ID starting with `C` (public), call `join_channel` and retry once; do not retry for `D`/`G` IDs
- [x] 3.3 Unit tests: auto-join success path, auto-join failure path, private-channel skip path

## 4. MCP tool registration

- [x] 4.1 In `errand/mcp_server.py`, register a `slack_message` tool that loads the bot token, resolves the target, checks the allowlist, posts via SlackClient, and returns `{ok, channel, ts, error?}`
- [x] 4.2 In `errand/mcp_server.py`, register a `slack_reply` tool that takes `channel`, `thread_ts`, `text`, optional `blocks`, checks the allowlist on `channel`, and posts via SlackClient with `thread_ts` set
- [x] 4.3 Surface Slack errors faithfully: `channel_not_found`, `not_in_channel`, `user_not_found`, `missing_scope`, etc. — wrap each in the `error` field of the return object
- [x] 4.4 Translate HTTP 429 into `{ok: false, error: "rate_limited; retry after <N> seconds"}` using the `Retry-After` header; do not retry server-side
- [x] 4.5 Emit info-level audit logs on every call: `task_id`, resolved target ID, `thread_ts` (if any), returned `ts` on success, error code on failure
- [x] 4.6 Confirm the MCP server identifies the calling task (existing auth path) so `task_id` can be included in audit logs; if not currently available, plumb it through

## 5. Tool exposure to task-runner

- [x] 5.1 Confirm both new tools appear in the task-runner's MCP catalog and are reachable via `discover_tools` without code changes in `task-runner/`
- [x] 5.2 Decide on hot-vs-catalog: leave catalog-only for v1 (no change to `DEFAULT_HOT_TOOLS`); record the decision in a code comment near the registration site
- [ ] 5.3 Manual smoke test in dev: spin up via `docker compose -f testing/docker-compose.yml up --build`, run a simple task that calls `slack_message` to a test channel, verify the message lands and the audit log appears

## 6. Slack scopes audit

- [ ] 6.1 Inventory current bot scopes against required set: `chat:write`, `chat:write.public`, `im:write`, `users:read`, `users:read.email`, `channels:read`, `groups:read`, `channels:join`
- [ ] 6.2 Update the bot manifest (or document the required re-install) for any missing scopes
- [ ] 6.3 Note in release notes / `CLAUDE.md` if a re-install of the Slack app is required after this change ships

## 7. Tests

- [x] 7.1 Unit tests for `slack_message` MCP handler: post by channel ID, post by channel name, DM by user ID, DM by username, DM by email, blocks-only payload, mixed text+blocks, allowlist rejection, auto-join, rate-limit translation
- [x] 7.2 Unit tests for `slack_reply` MCP handler: thread reply success, allowlist check on `channel`, missing `thread_ts` error
- [x] 7.3 Confirm the bot token never appears in MCP request payloads observable to the runner (assert in test by inspecting the tool registration / response shape)
- [x] 7.4 Run the full test suite locally with the errand venv: `DATABASE_URL="sqlite+aiosqlite:///:memory:" errand/.venv/bin/python -m pytest errand/tests/ -v`

## 8. Documentation & release

- [x] 8.1 Update `CLAUDE.md` Slack section to describe the new outbound tools and the `slack_outbound_allowlist` setting
- [ ] 8.2 Update `README.md` if it documents Slack capabilities at a high level
- [ ] 8.3 Add a short note to release notes covering the new tools, allowlist default, and any required scope/manifest changes
- [x] 8.4 Bump `VERSION` (MINOR) before opening the PR
