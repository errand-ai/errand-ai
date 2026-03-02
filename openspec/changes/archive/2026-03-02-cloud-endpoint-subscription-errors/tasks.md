## 1. Backend — Endpoint Error Persistence

- [x] 1.1 In `cloud_endpoints.py`, log the response body on non-2xx status before raising (already partially done in debug branch — make permanent)
- [x] 1.2 In `cloud_endpoints.py`, after a registration failure, store `{detail: str, timestamp: float}` in the `cloud_endpoint_error` Setting
- [x] 1.3 In `cloud_endpoints.py`, after a successful registration, delete the `cloud_endpoint_error` Setting if it exists
- [x] 1.4 In `main.py` `cloud_auth_disconnect`, delete the `cloud_endpoint_error` Setting as part of disconnect cleanup

## 2. Backend — Subscription Status API

- [x] 2.1 In `cloud_endpoints.py` (or a new `cloud_subscription.py`), add `fetch_subscription_status(cloud_creds, cloud_service_url) -> dict | None` that calls `GET /api/subscription` with Bearer auth and returns `{active, expires_at}` or `None` on failure
- [x] 2.2 In `main.py` `cloud_status` endpoint, call `fetch_subscription_status` when connected and include the result as `subscription` in the response (omit the key if None)
- [x] 2.3 In `main.py` `cloud_status` endpoint, read the `cloud_endpoint_error` Setting and include `endpoint_error: {detail}` in the response when present

## 3. Frontend — Endpoint Error UI

- [x] 3.1 In `CloudServicePage.vue`, extend the `CloudStatus` interface to include optional `endpoint_error?: {detail: string}` and `subscription?: {active: boolean, expires_at: string | null}`
- [x] 3.2 In `CloudServicePage.vue` `onMounted`, if `cloudStatus.value.endpoint_error` is set after `fetchStatus()`, fire `toast.error('Endpoint registration failed: ' + detail)`
- [x] 3.3 In `CloudServicePage.vue` template, replace the single `v-else-if` "Registering..." paragraph with three states: (a) `hasEndpoints` → show endpoint list, (b) `endpoint_error && !hasEndpoints` → show inline error, (c) `slack_configured && !hasEndpoints && !endpoint_error` → show "Registering..."

## 4. Frontend — Subscription Display

- [x] 4.1 In `CloudServicePage.vue`, add a `subscriptionExpiry` computed that formats `cloudStatus.value.subscription?.expires_at` as a readable date string (e.g. "15 Apr 2026"), or returns `null` when absent
- [x] 4.2 In `CloudServicePage.vue` connected-state template block, add subscription expiry display below the green connected indicator when `subscriptionExpiry` is non-null
- [x] 4.3 In `CloudServicePage.vue` connected-state template block, add a warning message when `subscription?.active === false`

## 5. Tests

- [x] 5.1 Add backend tests for `cloud_endpoint_error` setting being written on registration failure and cleared on success
- [x] 5.2 Add backend tests for `GET /api/cloud/status` including `endpoint_error` and `subscription` fields
- [x] 5.3 Update frontend tests in `CloudServicePage.test.ts` for the endpoint error state (toast + inline error, no "Registering..." shown)
- [x] 5.4 Add frontend tests for subscription expiry display and inactive subscription warning
