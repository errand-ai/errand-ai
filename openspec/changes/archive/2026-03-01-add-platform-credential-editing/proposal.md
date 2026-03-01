## Why

When a platform is connected, the only way to change configuration fields (task profile, poll interval, authorized recipients) is to disconnect — which deletes all stored credentials — and re-enter everything from scratch. This is frustrating for fields that don't affect the connection itself, especially for platforms like email where re-entering IMAP/SMTP credentials and passwords is tedious.

## What Changes

- Add a PATCH endpoint for partial credential updates that merges new values with existing encrypted credentials
- Distinguish between "connection" fields (require re-verification on change) and "configuration" fields (update without re-verification)
- Add an "Edit" button to connected platform cards that shows an inline form for configuration fields only
- Return non-sensitive configured field values to the frontend so the edit form can be pre-populated
- Add `editable` property to credential schema fields so platforms can declare which fields are safely editable post-connection

## Capabilities

### New Capabilities

- `platform-credential-editing`: Backend PATCH endpoint for partial credential updates with field-level classification (connection vs configuration), and frontend inline editing UI for connected platforms

### Modified Capabilities

- `platform-credentials`: Add PATCH endpoint for partial updates; extend GET response to return non-sensitive field values for connected platforms
- `platform-credentials-ui`: Add edit mode for connected platforms showing editable configuration fields with pre-populated values

## Impact

- **Backend**: New PATCH route in `main.py`; extend GET credentials response to include field values; add `editable` field property to credential schema
- **Frontend**: `PlatformSettings.vue` gains edit mode toggle; `PlatformCredentialForm.vue` supports pre-populated values and field filtering (editable-only mode)
- **Platform definitions**: Each platform's `credential_schema` gains `editable: true` on configuration fields (e.g., `email_profile`, `poll_interval`, `authorized_recipients`)
- **No database migration** — PlatformCredential model unchanged; encrypted_data blob is updated in place
