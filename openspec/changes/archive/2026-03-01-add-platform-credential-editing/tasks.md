## 1. Credential Schema: Editable Field Classification

- [x] 1.1 Add `"editable": true` to `email_profile`, `poll_interval`, and `authorized_recipients` fields in `EmailPlatform.info()` credential_schema (`errand/platforms/email.py`)
- [x] 1.2 Update `PlatformCredentialForm.vue` to recognize the `editable` field property (no behavior change yet, just pass-through)

## 2. Backend: PATCH Endpoint

- [x] 2.1 Add `PATCH /api/platforms/{platform_id}/credentials` endpoint in `errand/main.py` — decrypt existing credentials, validate that only `editable` fields are in the request, merge, re-encrypt, store without re-verification
- [x] 2.2 Return HTTP 400 if request contains non-editable fields, no credentials exist, or platform not found (404)

## 3. Backend: Extend GET Response

- [x] 3.1 Extend `GET /api/platforms/{platform_id}/credentials` response to include `field_values` dict with current values of `editable: true` fields only
- [x] 3.2 Return empty `field_values: {}` when no credentials are stored or platform has no editable fields

## 4. Frontend: Edit Mode

- [x] 4.1 Add `editableOnly` prop and `initialValues` prop to `PlatformCredentialForm.vue` — when `editableOnly` is true, filter schema to only show `editable: true` fields and pre-populate with `initialValues`
- [x] 4.2 Add `patchPlatformCredentials(platformId, fields)` API function in `useApi.ts` calling `PATCH /api/platforms/{platform_id}/credentials`
- [x] 4.3 Add "Edit" button to connected platform cards in `PlatformSettings.vue` — only show if platform has editable fields in schema
- [x] 4.4 Implement edit mode toggle in `PlatformSettings.vue` — clicking "Edit" fetches current `field_values` from GET and shows `PlatformCredentialForm` in `editableOnly` mode with pre-populated values
- [x] 4.5 Wire "Save" in edit mode to call PATCH endpoint, close form on success, show toast

## 5. Tests

- [x] 5.1 Add backend tests for PATCH endpoint — update editable field, reject non-editable field, no credentials, unknown platform
- [x] 5.2 Add backend tests for extended GET response — `field_values` with editable fields, empty when no credentials
- [x] 5.3 Add frontend tests for edit mode — Edit button visibility, form filtering, pre-population, save calls PATCH, cancel closes form
