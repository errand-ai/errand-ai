## Context

The setup wizard's "Test Connection" button (step 2) and the UserManagementPage's OIDC "Test Connection" button both use `toast.success()` for success feedback and inline error text for failure feedback. The toast may not be noticed on the full-page setup wizard layout, leaving users with no visible confirmation that the test succeeded.

The error path sets `step2Error` / `oidcError` reactive refs which render as inline red text near the button. There is no equivalent inline success indicator.

## Goals / Non-Goals

**Goals:**
- Add inline success feedback visible directly below the test connection buttons
- Keep existing toast calls for consistency with the rest of the app
- Match the visual pattern of inline error messages (text near the action)

**Non-Goals:**
- Changing the toast system or its z-index/positioning
- Adding connection test retry logic or progress indicators
- Modifying the backend `/api/llm/models` or OIDC discovery endpoints

## Decisions

1. **Inline success text**: Add a green success message (e.g., "Connection successful") rendered in the same position as error messages, using a `step2Success` / `oidcSuccess` reactive ref. This mirrors the `step2Error` / `oidcError` pattern.

2. **Clear on re-test**: When `testConnection()` / `testOidcConnection()` is called, clear both the error and success refs so stale feedback doesn't persist.

3. **Keep the toast**: Retain the existing `toast.success()` calls — they provide a secondary notification. The inline text is the primary feedback.

4. **Button state change**: After a successful test, show a green checkmark icon on the "Test Connection" button text (e.g., "Connection Verified ✓") to reinforce the success state. Reset when provider URL or API key inputs change.

## Risks / Trade-offs

- **Dual feedback (inline + toast)**: Slightly redundant, but the toast is non-blocking and disappears, while inline text persists — worth keeping both.
- **Reset on input change**: Clearing `connectionTested` when inputs change avoids stale success state but requires the user to re-test, which is the correct behavior.
