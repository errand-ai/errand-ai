## Context

Errand's platform abstraction supports social/messaging platforms (Twitter, Slack, GitHub) with credential management, verification, and a registry. The task-runner agent can create tasks and post to platforms via MCP tools. Background tasks (scheduler, Slack status updater, version checker) run as `asyncio.create_task()` in the main server lifespan.

Task profiles (`TaskProfile` model) define per-task configuration: system prompt, model, max turns, MCP servers, and skills. Tasks are linked to profiles via `profile_id`.

The email platform introduces a new pattern: a background poller that creates tasks from external events (incoming emails), combined with MCP tools that let the agent interact with the mailbox during task processing.

## Goals / Non-Goals

**Goals:**

- Enable errand to monitor a dedicated mailbox and create tasks from new emails
- Give the task-runner agent MCP tools to read, send, forward, and organise email
- Enforce security constraints: authorised recipients for outbound, blocked folders for moves, no delete/reply
- Support standard IMAP/SMTP with username/password or app passwords for broad provider compatibility
- Use IMAP IDLE for near-real-time email detection with polling as fallback
- Allow the user to select a task profile for email processing via the platform credentials UI

**Non-Goals:**

- OAuth2/XOAUTH2 authentication (future enhancement for Gmail/Outlook)
- Attachment binary handling (text-only for now; metadata included but not content)
- Multiple mailbox support (single email platform instance; multiple mailboxes deferred)
- Replying to email senders
- Deleting emails

## Decisions

### Decision 1: IMAP/SMTP over provider-specific APIs

Use standard IMAP4 for reading and SMTP for sending, rather than provider-specific APIs (Gmail API, Microsoft Graph).

**Rationale**: IMAP/SMTP works with any provider — Gmail (app passwords), Outlook, Fastmail, self-hosted Dovecot, ProtonMail Bridge. Provider-specific APIs require per-provider OAuth client registration and token refresh flows, which limits who can use the feature.

**Alternative considered**: Gmail API via service account. Rejected because it locks out non-Google users and adds OAuth2 complexity.

### Decision 2: `aioimaplib` for IMAP, `aiosmtplib` for SMTP

Use `aioimaplib` (async IMAP4 with native IDLE support) for all mailbox operations. Use `aiosmtplib` (async SMTP) for sending.

**Rationale**: The codebase is fully async. `aioimaplib` handles IDLE natively in the asyncio event loop — no threads needed. `IMAPClient` would require `asyncio.to_thread()` wrappers and a thread blocked on IDLE. `aiosmtplib` is the standard async SMTP library.

**Alternative considered**: `IMAPClient` with `asyncio.to_thread()`. Rejected because IDLE support requires a persistent blocked thread, which is less clean than native async IDLE.

**Trade-off**: `aioimaplib` has a lower-level API (closer to raw IMAP commands) than `IMAPClient`. We wrap it in a helper class to provide a clean interface. `aioimaplib` does not support XOAUTH2, which is acceptable since OAuth2 is a non-goal for v1.

### Decision 3: IMAP IDLE with polling fallback

The poller checks the server's CAPABILITY response for IDLE support:

- **IDLE supported**: Enter IDLE, wait for notification or timeout (configurable, e.g. 10 minutes). On notification or timeout, exit IDLE, process new messages, re-enter IDLE. Safety poll (full UNSEEN check) every N cycles.
- **IDLE not supported**: Poll at the configured interval (minimum 60 seconds).

**Rationale**: IDLE provides near-instant email detection without repeated polling. Gmail drops IDLE connections after ~10 minutes and RFC 2177 recommends re-issuing every 29 minutes, so periodic re-entry is required regardless. The polling fallback ensures compatibility with servers that don't support IDLE.

### Decision 4: Poller runs in the main server process

The email poller runs as `asyncio.create_task(run_email_poller(...))` in the main server lifespan, alongside `run_scheduler()`, `run_status_updater()`, and `run_version_checker()`.

**Rationale**: The poller is lightweight — it checks for unread messages and creates tasks. The heavy processing (email analysis, follow-up task creation) happens in the task-runner worker. This matches the existing pattern where the scheduler promotes tasks and the worker processes them.

### Decision 5: Email-to-task creation flow

1. Poller fetches UNSEEN messages from INBOX
2. For each message: check IMAP UID against existing tasks (dedup via `created_by="email_poller"` and UID stored in task metadata/description)
3. Convert email body (HTML or plain text) to markdown using `html2text`
4. Create task with: title from subject line, description containing email metadata + markdown body, `profile_id` from configured email profile, `created_by="email_poller"`
5. Mark message as `\Seen` on the IMAP server
6. Publish `task_created` WebSocket event

Messages are marked read immediately after task creation (not after agent processing). The task is the durable record — if agent processing fails, the task remains for retry.

### Decision 6: Credential schema with `profile_select` field type

Email platform credentials include IMAP/SMTP connection settings, authentication, and email-specific configuration (task profile, poll interval, authorised recipients) in a single credential schema:

```python
credential_schema = [
    {"key": "imap_host", "label": "IMAP Server", "type": "text", "required": True},
    {"key": "imap_port", "label": "IMAP Port", "type": "text", "required": True},
    {"key": "smtp_host", "label": "SMTP Server", "type": "text", "required": True},
    {"key": "smtp_port", "label": "SMTP Port", "type": "text", "required": True},
    {"key": "security", "label": "Security", "type": "select", "options": [
        {"label": "SSL/TLS", "value": "ssl"},
        {"label": "STARTTLS", "value": "starttls"},
    ]},
    {"key": "username", "label": "Email Address", "type": "text", "required": True},
    {"key": "password", "label": "Password / App Password", "type": "password", "required": True},
    {"key": "email_profile", "label": "Task Profile", "type": "profile_select", "required": True},
    {"key": "poll_interval", "label": "Poll Interval (seconds)", "type": "text", "required": False,
     "help_text": "Minimum 60. Reduced when IMAP IDLE is supported."},
    {"key": "authorized_recipients", "label": "Authorised Recipients", "type": "textarea",
     "required": False, "help_text": "One email per line. Agent can only send/forward to these."},
]
```

A new `profile_select` field type in `PlatformCredentialForm.vue` fetches profiles from `GET /api/profiles` and renders a dropdown. This is the only frontend change needed.

**Alternative considered**: Separate email-specific settings from IMAP/SMTP credentials (different storage, different UI). Rejected — keeping everything in one credential blob simplifies the platform model and UI.

### Decision 7: Security constraints enforced server-side

**Authorised recipients**: `send_email` and `forward_email` MCP tools load the `authorized_recipients` list from email platform credentials. If the `to` address is not in the list, the tool returns an error. This is enforced in the MCP tool handler, not by the agent.

**Blocked folders**: `move_email` checks the target folder against a blocklist of known trash/junk folder names and IMAP `SPECIAL-USE` attributes (RFC 6154). Known patterns: `Trash`, `Deleted Items`, `[Gmail]/Trash`, `Junk`, `Spam`, `Junk Email`, `[Gmail]/Spam`. The tool also checks for `\Trash` and `\Junk` SPECIAL-USE attributes.

**No delete**: No `delete_email` MCP tool is implemented. The `move_email` tool's folder blocklist prevents moving to trash as a workaround.

**No reply**: No `reply_email` MCP tool is implemented. `send_email` creates new messages only — it cannot set `In-Reply-To` or `References` headers.

### Decision 8: HTML to markdown conversion

Email bodies are converted to markdown using `html2text` (same dependency used by the `read_url` tool from the SearXNG change). For multipart messages, prefer `text/html` part and convert; fall back to `text/plain` if no HTML part exists.

**Rationale**: Most modern emails are HTML. Converting to markdown preserves structure (headers, links, lists) while being LLM-friendly.

## Risks / Trade-offs

- **[IMAP connection stability]** IDLE connections can drop silently, especially through NATs/firewalls. → The poller re-enters IDLE on a timeout and does safety polls. Connection errors trigger reconnection with backoff.
- **[aioimaplib maturity]** Lower-level API than IMAPClient, less battle-tested against edge cases. → Wrap in a helper class with error handling. The operations we need (FETCH, STORE, COPY, SELECT, IDLE, LIST) are well-covered by the library.
- **[Gmail app password UX]** Users must enable 2FA and create an app password in Google account settings. → Document the setup flow in help text on the credential form.
- **[Large email bodies]** Some emails (newsletters, marketing) can be very large. → Truncate the markdown body to a configurable max length (e.g. 50,000 chars) when creating the task description.
- **[Poll interval enforcement]** Users could set a very low interval and hit provider rate limits. → Enforce minimum 60 seconds in the poller. When IDLE is active, the poll interval only affects the safety poll frequency (not the IDLE re-entry).
- **[Credential form complexity]** 10 fields is a lot for one form. → The existing form renders cleanly with labels, help text, and the mode toggle. Consider grouping with visual separators in a future UI enhancement.
