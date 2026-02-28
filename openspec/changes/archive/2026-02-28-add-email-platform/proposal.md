## Why

The task-runner agent needs to process incoming emails — analysing content, creating follow-up tasks, forwarding to authorised recipients, and organising messages into folders. Errand should have its own dedicated mailbox (not the user's personal inbox) with a background poller that creates tasks from new messages using a configurable task profile and system prompt.

## What Changes

- Create `EmailPlatform` implementing the platform abstraction with IMAP/SMTP credentials and email-specific settings (task profile, poll interval, authorised recipients)
- Add a background email poller that checks for unread messages using IMAP IDLE (with polling fallback), creates tasks from new emails, and marks them as read
- Add 6 MCP tools for the task-runner agent: `list_emails`, `read_email`, `list_email_folders`, `move_email`, `send_email`, `forward_email`
- Security constraints: send/forward restricted to authorised recipients only, move blocked from Trash/Junk folders, no delete or reply capabilities
- Email bodies (HTML and plain text) converted to markdown for task descriptions
- Add a `profile_select` field type to the platform credential form for linking a task profile to the email platform
- Add `aioimaplib` and `aiosmtplib` as Python dependencies

## Capabilities

### New Capabilities

- `email-platform`: Email platform integration with IMAP/SMTP credentials, connection verification, and platform registration
- `email-poller`: Background poller using IMAP IDLE with polling fallback that creates tasks from unread emails with deduplication
- `email-mcp-tools`: MCP tools for reading, sending, forwarding, and organising email with security constraints
- `email-credential-ui`: New `profile_select` field type in the platform credential form for dynamic task profile selection

### Modified Capabilities

- `platform-abstraction`: Add `EMAIL` to `PlatformCapability` enum
- `mcp-server-endpoint`: Add `list_emails`, `read_email`, `list_email_folders`, `move_email`, `send_email`, `forward_email` to MCP tool list
- `platform-credentials-ui`: Add `profile_select` field type rendering with dynamic profile data

## Impact

- **Backend**: New `errand/platforms/email.py` module, new `errand/email_poller.py` module; modifications to `errand/platforms/base.py`, `errand/mcp_server.py`, `errand/main.py`
- **Dependencies**: `aioimaplib` (async IMAP with IDLE support), `aiosmtplib` (async SMTP) added to `errand/requirements.txt`
- **Frontend**: New `profile_select` field type in `PlatformCredentialForm.vue` (fetches profiles from `GET /api/profiles`)
- **Database**: No schema changes — email platform uses existing `PlatformCredential` model; task profile linkage via credential data
- **Deployment**: Email polling runs as a background task in the main server process alongside the scheduler
