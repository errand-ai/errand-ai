## Why

On the setup wizard's LLM Provider Configuration page (step 2), clicking "Test Connection" gives no visible feedback on success. The success path calls `toast.success()`, but the toast may not be noticeable on the full-page setup layout. Error feedback uses inline text (`step2Error`), creating an inconsistency — failures are obvious, successes are invisible.

## What Changes

- Add inline visual success feedback to the "Test Connection" button on the setup wizard's LLM Provider step, matching the inline error feedback pattern
- The same issue exists on the UserManagementPage OIDC "Test Connection" button — fix both for consistency

## Capabilities

### New Capabilities

_(none)_

### Modified Capabilities

- `admin-settings-ui`: Add inline success feedback requirement for "Test Connection" actions

## Impact

- **Frontend**: `SetupWizard.vue` (step 2 test connection), `UserManagementPage.vue` (OIDC test connection)
- **Tests**: `SetupWizard.test.ts` — add assertion for success feedback visibility
