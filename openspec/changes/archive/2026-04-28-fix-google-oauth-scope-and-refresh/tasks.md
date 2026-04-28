## Tasks

### Bug 1 — OIDC scope canonicalisation

- [x] In `errand/integration_routes.py`, replace the short OIDC entries in `GOOGLE_WORKSPACE_SCOPES`:
  - `email` → `https://www.googleapis.com/auth/userinfo.email`
  - `profile` → `https://www.googleapis.com/auth/userinfo.profile`
  - keep `openid` as-is (Google preserves the short form for this one).
- [x] Coordinate with the errand-cloud change `align-oidc-canonical-scopes` so the cloud-side `_GOOGLE_WORKSPACE_SCOPES` matches. Without that, errand-cloud's authorize redirect to Google will request the short form and we'll get the same skew via the cloud-proxy direct flow.
- [x] Verify `_required_scopes("google_drive").issubset(persisted granted_scopes)` after the next re-auth — `reauth_required` should flip to `false` and the Settings UI should drop the Re-authorize button.

### Bug 2 — Wire-name canonicalisation

- [x] In `errand/integration_routes.py:authorize`, send `to_wire_provider(provider)` instead of `provider` on the `oauth_initiate` WebSocket frame (revert the workaround from commit `9a69353`).
- [x] In `errand/integration_routes.py:refresh_token`, swap the `provider` argument to `client.send_and_await(...)` for `to_wire_provider(provider)` on both the `message["provider"]` field and the `provider=` waiter key. Same reasoning.
- [x] In `authorize`, switch the `redirect_url` returned to the browser to use `to_wire_provider(provider)` in the path: `f"{cloud_service_url}/oauth/{to_wire_provider(provider)}/authorize?state={state}"`. errand-cloud's `…/oauth/google_workspace/callback` is now registered with Google.

### Tests

- [x] Update `test_authorize_cloud_proxy_provider_name` (current: legacy `google_drive` on the WS frame) to assert the canonical `google_workspace` again, and to assert the redirect URL uses the canonical path. Rename back to `test_authorize_cloud_proxy_uses_canonical_provider`.
- [x] Update `test_authorize_google_drive` to use the canonical OIDC URIs in its scope assertions (`userinfo.email`, `userinfo.profile`) and to remove the short-form assertions.
- [x] Add a regression test for `_required_scopes("google_drive").issubset(...)` against a stub `granted_scopes` list that mirrors what Google actually returns (canonical URIs plus the Workspace scopes).

### Local verification

- [x] After deploying both this change and `align-oidc-canonical-scopes`:
  - re-auth via the cloud flow once.
  - confirm the Re-authorize button disappears on Settings → Integrations.
  - confirm `kubectl logs errand-server | grep refresh` no longer emits `Timeout waiting for oauth_refresh_result response for google_drive`.
  - confirm a new task-runner pod has `GOOGLE_WORKSPACE_CLI_TOKEN` injected and `gws-*` skills mounted at `/workspace/skills/`.

### Spec + version

- [x] Update `openspec/specs/cloud-storage-oauth/spec.md` with the canonical OIDC scope list and the canonical-on-the-wire requirement.
- [x] Bump `VERSION` (patch — bug fix).
