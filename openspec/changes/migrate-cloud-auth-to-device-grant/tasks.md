## 1. Backend — device grant client

errand-cloud's endpoints are already deployed at `https://errand.cloud`, so every task here can be exercised against the live service from the start. The contract:

- `POST /auth/tenant/device/code` → `{device_code, user_code, verification_uri, verification_uri_complete, expires_in, interval}`
- `POST /auth/tenant/device/token` with `{"device_code": "…"}` → 200 with `{access_token, refresh_token, expires_in, token_type}`, or 400 with `{"error": "authorization_pending" | "slow_down" | "expired_token" | "access_denied"}`

- [ ] 1.1 Write failing tests for `cloud_auth.py`: initiation returns the display fields; polling maps each of the four error codes to a distinct outcome; a 200 yields tokens
- [ ] 1.2 Add `request_device_code(cloud_url)` and `poll_device_token(cloud_url, device_code)` to `errand/cloud_auth.py`
- [ ] 1.3 Write failing tests for the poller: it waits the advertised interval, backs off further on `slow_down`, stops on `access_denied` and `expired_token`, and stops when the grant's own expiry passes
- [ ] 1.4 Implement the polling task, bounded by `expires_in` so it cannot outlive the grant
- [ ] 1.5 Surface an HTTP 429 from the cloud as an error rather than tightening the loop — the cloud rate limits these endpoints (initiation 10/min, polling 60/min per IP)

## 2. Backend — endpoints

- [ ] 2.1 Write failing tests: `POST /api/cloud/auth/device` requires the `admin` role, returns the verification fields, and never returns the device code
- [ ] 2.2 Replace `cloud_auth_login` with `POST /api/cloud/auth/device`, dropping the `cloud_auth_state` nonce
- [ ] 2.3 Write failing tests for `GET /api/cloud/auth/device/status` covering pending, connected, denied, expired, error, and none-in-progress
- [ ] 2.4 Implement the status endpoint
- [ ] 2.5 Write a failing test that a second initiation abandons the first pending grant rather than refusing
- [ ] 2.6 On success, reuse the existing credential path unchanged — `sub` as tenant_id, encrypted `PlatformCredential`, WebSocket client start, endpoint registration. Assert against the existing tests rather than writing new ones for behaviour that has not changed
- [ ] 2.7 Remove `GET /api/cloud/auth/callback` and the now-unused `exchange_code` in `cloud_auth.py`
- [ ] 2.8 Confirm no remaining reference to `cloud_auth_state`, and that a stale row is inert if one exists

## 3. Frontend

- [ ] 3.1 Replace the popup in `frontend/src/pages/settings/CloudServicePage.vue` with an in-page panel showing the verification code in large type and the verification URI as a link
- [ ] 3.2 Use `verification_uri_complete` for the link so a click on the same machine needs no retyping, while still showing the bare code for a different device
- [ ] 3.3 Poll `GET /api/cloud/auth/device/status` and reflect connected, denied and expired distinctly
- [ ] 3.4 Restore the pending state on reload from the status endpoint, so a refresh does not lose an in-flight grant
- [ ] 3.5 Confirm the disconnect path and the connected-state UI are untouched

## 4. Verify against the live service

- [ ] 4.1 `uv run pytest` passes
- [ ] 4.2 Complete a real device grant against `https://errand.cloud` from this instance and confirm it reaches `status = "connected"`
- [ ] 4.3 Confirm the cloud served `POST /auth/tenant/device/code` and `POST /auth/tenant/device/token` for it — check the request log, not just the UI. **A working UI is not evidence the new flow ran**: during the cloud-side verification an instance appeared connected while actually coasting on a pre-existing refresh token, with neither endpoint ever having been called
- [ ] 4.4 Confirm the WebSocket client connects and cloud endpoints register, as they did under the redirect flow
- [ ] 4.5 Confirm an already-connected instance was not forced to re-authenticate

## 5. Close S1 in production

This is the point of the change. Do not stop at task 4.

- [ ] 5.1 Delete the `tenantAuth.allowForeignRedirect: true` block from `errand-cloud-values.yaml` in `devops-consultants/argocd` and let ArgoCD sync
- [ ] 5.2 Confirm `GET https://errand.cloud/auth/tenant/login?redirect_uri=https://errand.devops-consultants.net/…` now returns HTTP 400
- [ ] 5.3 Confirm this instance still authenticates after that removal — it must, since it no longer sends a `redirect_uri`
- [ ] 5.4 Confirm errand-cloud stops logging the `TENANT_LOGIN_ALLOW_FOREIGN_REDIRECT` warning
- [ ] 5.5 Tick tasks 1.11 and 1.12 in errand-cloud's `harden-auth-and-public-endpoints` change, and note on errand-ai/errand-cloud#25 that S1 is now closed in production rather than only in code

## 6. Finalize

- [ ] 6.1 Bump `VERSION`
- [ ] 6.2 Confirm each delta spec scenario is satisfied, or recorded as unverified with a reason
- [ ] 6.3 Open a PR referencing errand-ai/errand-cloud#73 and #25
