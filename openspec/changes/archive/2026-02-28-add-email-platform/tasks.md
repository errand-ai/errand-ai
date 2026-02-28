## 1. Platform Abstraction

- [x] 1.1 Add `EMAIL = "email"` to `PlatformCapability` enum in `errand/platforms/base.py`

## 2. Email Platform

- [x] 2.1 Create `errand/platforms/email.py` with `EmailPlatform` class implementing `info()` with full credential schema (IMAP/SMTP connection, security, auth, profile_select, poll_interval, authorized_recipients)
- [x] 2.2 Implement `verify_credentials()` — connect to IMAP (SSL/TLS or STARTTLS), SELECT INBOX, then verify SMTP connectivity
- [x] 2.3 Register `EmailPlatform` in app startup in `errand/main.py`

## 3. Email Poller

- [x] 3.1 Create `errand/email_poller.py` with IMAP connection helper — connect, login, handle SSL/TLS vs STARTTLS, check IDLE capability
- [x] 3.2 Implement IMAP IDLE loop — enter IDLE, wait for notification or timeout, exit IDLE, process messages, re-enter
- [x] 3.3 Implement polling fallback — sleep for poll_interval (minimum 60s), fetch UNSEEN messages
- [x] 3.4 Implement unread message processing — fetch UNSEEN from INBOX, extract UID/from/to/subject/date/body
- [x] 3.5 Implement email body conversion — prefer text/html → markdown via html2text, fallback to text/plain, truncate to 50,000 chars
- [x] 3.6 Implement task creation from email — create task with subject as title, metadata + markdown body as description, configured profile_id, created_by="email_poller", publish task_created event
- [x] 3.7 Implement duplicate detection — check IMAP UID against existing email_poller tasks before creating
- [x] 3.8 Implement mark-as-read — add \Seen flag after successful task creation
- [x] 3.9 Implement connection error resilience — reconnection with exponential backoff (5s to 5min)
- [x] 3.10 Add `run_email_poller()` as `asyncio.create_task()` in main.py lifespan

## 4. Email MCP Tools

- [x] 4.1 Add `list_emails` MCP tool — connect to IMAP, fetch message summaries from specified folder with optional search, return JSON
- [x] 4.2 Add `read_email` MCP tool — fetch full message by UID, convert HTML body to markdown, include attachment metadata (no binary), return JSON
- [x] 4.3 Add `list_email_folders` MCP tool — list all IMAP folders with names and attributes, return JSON
- [x] 4.4 Add `move_email` MCP tool — COPY to target folder, STORE \Deleted + EXPUNGE on source, auto-create folder if needed, enforce blocked folder check
- [x] 4.5 Implement blocked folder detection — blocklist of trash/junk patterns (case-insensitive, final path component), SPECIAL-USE attribute check (\Trash, \Junk)
- [x] 4.6 Add `send_email` MCP tool — validate recipient against authorized_recipients, send via SMTP, no In-Reply-To/References headers, return JSON
- [x] 4.7 Add `forward_email` MCP tool — validate recipient, fetch original message, create forwarded message with original headers/body, send via SMTP, return JSON

## 5. Frontend: Profile Select Field

- [x] 5.1 Add `profile_select` field type to `PlatformCredentialForm.vue` — fetch profiles from `GET /api/profiles` on mount, render as `<select>` dropdown with profile name as label and ID as value
- [x] 5.2 Handle empty profiles state — show message indicating a task profile must be created first

## 6. Dependencies

- [x] 6.1 Add `aioimaplib` and `aiosmtplib` to `errand/requirements.txt`

## 7. Tests

- [x] 7.1 Add unit tests for `EmailPlatform` (info, verify_credentials) in `errand/tests/test_email_platform.py`
- [x] 7.2 Add unit tests for email poller (message processing, body conversion, duplicate detection, mark-as-read) in `errand/tests/test_email_poller.py`
- [x] 7.3 Add unit tests for email MCP tools (list_emails, read_email, list_email_folders, move_email, send_email, forward_email) in `errand/tests/test_mcp.py`
- [x] 7.4 Add unit tests for blocked folder detection (pattern matching, case-insensitive, SPECIAL-USE attributes)
- [x] 7.5 Add unit tests for authorized recipient enforcement (send_email, forward_email — authorised and unauthorised)
- [x] 7.6 Add frontend tests for profile_select field type in PlatformCredentialForm
