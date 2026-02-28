## Purpose

MCP tools for the task-runner agent to read, send, forward, and organise email in errand's dedicated mailbox, with security constraints on outbound messages and folder operations.

## ADDED Requirements

### Requirement: list_emails MCP tool

The MCP server SHALL expose a `list_emails` tool that accepts `folder` (str, optional, default "INBOX"), `limit` (int, optional, default 20), and `search` (str, optional, IMAP search criteria). The tool SHALL connect to the configured IMAP server, fetch message summaries (UID, from, to, subject, date, flags), and return a JSON string with a `messages` array. If no email platform is configured, the tool SHALL return an error.

#### Scenario: List inbox messages

- **WHEN** `list_emails()` is called with default parameters
- **THEN** the tool returns up to 20 messages from INBOX with UID, from, to, subject, date, and flags

#### Scenario: List messages in a specific folder

- **WHEN** `list_emails(folder="Invoices")` is called
- **THEN** the tool returns messages from the Invoices folder

#### Scenario: Search messages

- **WHEN** `list_emails(search="FROM acme@example.com")` is called
- **THEN** the tool returns messages matching the IMAP search criteria

#### Scenario: No email platform configured

- **WHEN** `list_emails()` is called and no email platform credentials exist
- **THEN** the tool returns a JSON string with an `error` key

### Requirement: read_email MCP tool

The MCP server SHALL expose a `read_email` tool that accepts `message_uid` (str, required) and `folder` (str, optional, default "INBOX"). The tool SHALL fetch the full message and return a JSON string with: `uid`, `from`, `to`, `cc`, `subject`, `date`, `body` (HTML converted to markdown, or plain text), and `attachments` (list of `{filename, content_type, size}` metadata only — no binary content).

#### Scenario: Read a message

- **WHEN** `read_email(message_uid="1234")` is called
- **THEN** the tool returns the full message with headers, markdown body, and attachment metadata

#### Scenario: Read HTML email

- **WHEN** `read_email()` is called for an HTML email
- **THEN** the body is converted to markdown

#### Scenario: Message not found

- **WHEN** `read_email(message_uid="99999")` is called for a non-existent UID
- **THEN** the tool returns a JSON string with an `error` key

#### Scenario: Attachment metadata

- **WHEN** `read_email()` is called for a message with 2 PDF attachments
- **THEN** the `attachments` array contains 2 entries with filename, content_type, and size — no binary content

### Requirement: list_email_folders MCP tool

The MCP server SHALL expose a `list_email_folders` tool that accepts no parameters. The tool SHALL connect to the configured IMAP server, list all folders, and return a JSON string with a `folders` array containing `{name, attributes, delimiter}` for each folder.

#### Scenario: List folders

- **WHEN** `list_email_folders()` is called
- **THEN** the tool returns all IMAP folders with their names and attributes

#### Scenario: Gmail folder structure

- **WHEN** `list_email_folders()` is called against a Gmail IMAP server
- **THEN** the response includes folders like `INBOX`, `[Gmail]/Sent Mail`, `[Gmail]/Trash`, etc.

### Requirement: move_email MCP tool

The MCP server SHALL expose a `move_email` tool that accepts `message_uid` (str, required), `folder` (str, required), and `source_folder` (str, optional, default "INBOX"). The tool SHALL move the message to the target folder using IMAP COPY + STORE (add `\Deleted` flag on source) + EXPUNGE. If the target folder does not exist, the tool SHALL create it. The tool SHALL reject moves to blocked folders.

#### Scenario: Move email to existing folder

- **WHEN** `move_email(message_uid="1234", folder="Invoices")` is called
- **THEN** the message is copied to Invoices, deleted from INBOX, and success is returned

#### Scenario: Move email to new folder

- **WHEN** `move_email(message_uid="1234", folder="New Category")` is called and "New Category" does not exist
- **THEN** the folder is created, the message is moved, and success is returned

#### Scenario: Move to Trash blocked

- **WHEN** `move_email(message_uid="1234", folder="Trash")` is called
- **THEN** the tool returns an error: "Cannot move to Trash — deletion is not permitted"

#### Scenario: Move to Gmail Trash blocked

- **WHEN** `move_email(message_uid="1234", folder="[Gmail]/Trash")` is called
- **THEN** the tool returns an error

#### Scenario: Move to Junk/Spam blocked

- **WHEN** `move_email(message_uid="1234", folder="Junk")` is called
- **THEN** the tool returns an error

#### Scenario: Move to folder with Trash SPECIAL-USE attribute blocked

- **WHEN** `move_email()` targets a folder with the `\Trash` IMAP SPECIAL-USE attribute
- **THEN** the tool returns an error regardless of folder name

### Requirement: Blocked folder detection

The `move_email` tool SHALL maintain a blocklist of folder name patterns: `trash`, `deleted`, `deleted items`, `deleted messages`, `junk`, `spam`, `junk email`. Folder names SHALL be compared case-insensitively after extracting the final path component (e.g. `[Gmail]/Trash` → `trash`). The tool SHALL also check for `\Trash` and `\Junk` IMAP SPECIAL-USE attributes (RFC 6154) when available.

#### Scenario: Case-insensitive blocking

- **WHEN** `move_email()` targets a folder named "TRASH"
- **THEN** the move is blocked

#### Scenario: Nested folder path blocking

- **WHEN** `move_email()` targets a folder named "[Gmail]/Trash"
- **THEN** the final component "Trash" matches the blocklist and the move is blocked

### Requirement: send_email MCP tool

The MCP server SHALL expose a `send_email` tool that accepts `to` (str, required), `subject` (str, required), and `body` (str, required). The tool SHALL validate that `to` is in the `authorized_recipients` list from the email platform credentials. If authorised, the tool SHALL send the email via SMTP from the configured email address. The tool SHALL NOT set `In-Reply-To` or `References` headers. The tool SHALL return a JSON string indicating success or error.

#### Scenario: Send to authorised recipient

- **WHEN** `send_email(to="rob@example.com", subject="Report", body="...")` is called and `rob@example.com` is in `authorized_recipients`
- **THEN** the email is sent and success is returned

#### Scenario: Send to unauthorised recipient

- **WHEN** `send_email(to="stranger@example.com", ...)` is called and the address is not in `authorized_recipients`
- **THEN** the tool returns an error: "Recipient not in authorised recipients list"

#### Scenario: No authorised recipients configured

- **WHEN** `send_email()` is called and `authorized_recipients` is empty
- **THEN** the tool returns an error indicating no recipients are authorised

### Requirement: forward_email MCP tool

The MCP server SHALL expose a `forward_email` tool that accepts `message_uid` (str, required), `to` (str, required), and `folder` (str, optional, default "INBOX"). The tool SHALL validate that `to` is in the `authorized_recipients` list. If authorised, the tool SHALL fetch the original message, create a forwarded message with the original content as the body (prefixed with original headers), and send via SMTP. The tool SHALL return a JSON string indicating success or error.

#### Scenario: Forward to authorised recipient

- **WHEN** `forward_email(message_uid="1234", to="rob@example.com")` is called and the address is authorised
- **THEN** the original message is forwarded and success is returned

#### Scenario: Forward to unauthorised recipient

- **WHEN** `forward_email(message_uid="1234", to="stranger@example.com")` is called and the address is not authorised
- **THEN** the tool returns an error

#### Scenario: Forward non-existent message

- **WHEN** `forward_email(message_uid="99999", to="rob@example.com")` is called
- **THEN** the tool returns an error indicating the message was not found

### Requirement: No delete capability

The MCP server SHALL NOT expose any tool for deleting emails. There SHALL be no `delete_email` tool.

#### Scenario: No delete tool available

- **WHEN** a client sends a `tools/list` request to `/mcp`
- **THEN** no `delete_email` tool is listed

### Requirement: No reply capability

The MCP server SHALL NOT expose any tool for replying to email senders. There SHALL be no `reply_email` tool. The `send_email` tool SHALL NOT accept parameters for `In-Reply-To` or `References` headers.

#### Scenario: No reply tool available

- **WHEN** a client sends a `tools/list` request to `/mcp`
- **THEN** no `reply_email` tool is listed
