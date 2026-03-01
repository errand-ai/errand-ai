## Context

Platform credentials are stored as a single encrypted JSON blob per platform. The current API only supports full replacement (PUT) or deletion (DELETE). The frontend hides the credential form entirely once connected, with no way to update individual fields. This forces users to disconnect and re-enter all credentials to change a single configuration value like task profile or poll interval.

The email platform is the first platform with meaningful "configuration" fields that change frequently (task profile, poll interval, authorized recipients) alongside "connection" fields that rarely change (host, port, username, password).

## Goals / Non-Goals

**Goals:**
- Allow updating configuration fields (profile, poll interval, authorized recipients) without disconnecting
- Pre-populate the edit form with current non-sensitive field values
- Keep connection fields (host, port, username, password) hidden when editing — these require disconnect/reconnect to change
- Support field-level classification via `credential_schema` so each platform controls what's editable

**Non-Goals:**
- Changing connection fields without re-verification (always requires disconnect/reconnect)
- Exposing password or secret values back to the frontend
- Per-field verification (verification remains all-or-nothing)
- Audit trail for credential changes

## Decisions

### Decision: PATCH endpoint for partial updates

Add `PATCH /api/platforms/{platform_id}/credentials` that accepts a partial JSON object. The backend merges the provided fields into the existing decrypted credentials, re-encrypts, and stores. No re-verification is triggered for editable-only changes.

**Alternative considered**: Reuse PUT with a "partial" flag. Rejected because PUT semantics imply full replacement, and we need different behavior (no verification for config-only changes).

### Decision: `editable` property on credential schema fields

Each field in `credential_schema` can declare `"editable": true` to indicate it can be changed post-connection without re-verification. Fields without this property (or with `editable: false`) are connection fields that require disconnect/reconnect.

This keeps the classification in the platform definition where it belongs, rather than hardcoding field names in the frontend.

### Decision: Return non-sensitive field values via GET

Extend `GET /api/platforms/{platform_id}/credentials` to return actual values for `editable` fields (task profile, poll interval, authorized recipients) but never for sensitive fields (passwords, API keys). The frontend uses these to pre-populate the edit form.

The response adds a `field_values` dict containing only the values of `editable` fields. Sensitive connection fields are excluded.

**Alternative considered**: Return all field values with password fields masked. Rejected because it increases the attack surface — even masked values reveal field presence and length.

### Decision: Frontend inline edit form

When a platform is connected, an "Edit" button appears alongside "Verify" and "Disconnect". Clicking it shows a compact form with only the `editable` fields, pre-populated with current values from the GET response. Saving calls PATCH instead of PUT. The form has "Save" and "Cancel" buttons.

The edit form reuses `PlatformCredentialForm` with a new `editableOnly` mode that filters the schema to editable fields and pre-populates values.

## Risks / Trade-offs

- **Risk**: PATCH without re-verification could store invalid config values (e.g., bad profile_id) → Mitigation: profile_id is a UUID select, poll_interval has minimum enforcement on the backend, authorized_recipients is free-text. The values are validated at use time, not save time.
- **Risk**: Extending GET to return field values could leak sensitive data if `editable` is misconfigured → Mitigation: Only return values for fields explicitly marked `editable: true`. Default is false (secure by default).
- **Trade-off**: The edit form doesn't show connection field values (they're sensitive), so users can't see their IMAP host etc. This is intentional for security.
