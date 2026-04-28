## Why

After the Google Workspace integration shipped (PR #165) and errand-cloud was hardened to accept either provider name on the relay (PR `expand-google-oauth-scopes`), production exposed two distinct bugs that share a root: errand-server's request-vs-response asymmetry on the OAuth flow.

### Bug 1 — OIDC short-scope mismatch (UI permanently shows Re-authorize)

errand-server requests `email` and `profile` in `GOOGLE_WORKSPACE_SCOPES` and stores the same strings as the *required* set used by `_required_scopes()` for stale-scope detection. Google's token endpoint, however, **rewrites those short OpenID Connect scopes to their canonical Drive-style URIs** before returning the granted set:

| Requested | Returned by Google |
|-----------|--------------------|
| `email` | `https://www.googleapis.com/auth/userinfo.email` |
| `profile` | `https://www.googleapis.com/auth/userinfo.profile` |
| `openid` | `openid` |

`_required_scopes("google_drive").issubset(set(granted))` is therefore always false for `email` and `profile`, the integration status endpoint emits `reauth_required: true`, and the Settings → Integrations page never lets the user past the Re-authorize button — even after a successful re-auth that grants every Workspace scope. Verified in production 2026-04-28: the persisted `google_drive` credential's `granted_scopes` contains the 9 Workspace URIs plus `openid`, `userinfo.email`, `userinfo.profile`, missing only `email` and `profile` against a required set that still uses the short names.

### Bug 2 — Refresh waiter key mismatch (task-runner gets no Google token + no gws skills)

errand-server's `oauth_refresh` flow calls `client.send_and_await(message={"provider": provider}, response_type="oauth_refresh_result", provider=provider, timeout=30.0)`. After commit `9a69353` reverted the wire-name canonicalisation as a workaround for an earlier `redirect_uri_mismatch`, `provider` is `"google_drive"` (legacy). The waiter is registered at key `"oauth_refresh_result:google_drive"`.

errand-cloud's WebSocket handler, however, **always normalises the response provider to the canonical name** (`canonical_provider()`), so the inbound reply carries `"provider": "google_workspace"`. `_resolve_pending_response` keys by `f"{msg_type}:{provider}"`, so the lookup at `"oauth_refresh_result:google_workspace"` finds no waiter → 30 s timeout → `/api/integrations/google_drive/refresh` returns 502 → `_load_cloud_storage_credentials` drops Google → no `GOOGLE_WORKSPACE_CLI_TOKEN` env var, no gws system skills, no Google Workspace prompt instructions on the task-runner.

errand-cloud has been alias-tolerant on inbound for a while now and the operator has registered `…/oauth/google_workspace/callback` with Google. The original reasons for keeping the wire on legacy (`redirect_uri_mismatch`, "Provider mismatch") have all been resolved. We can flip back to canonical end-to-end and the asymmetry disappears.

## What Changes

- **Switch `GOOGLE_WORKSPACE_SCOPES` to use the canonical OpenID Connect URIs** (`https://www.googleapis.com/auth/userinfo.email`, `https://www.googleapis.com/auth/userinfo.profile`) so the request and the persisted required set match what Google echoes back. Requires a coordinated change in errand-cloud's matching scope list.
- **Send the canonical `google_workspace` name on `oauth_initiate` and `oauth_refresh` WebSocket frames** by re-applying `to_wire_provider(provider)` at both call sites, undoing the workaround in commit `9a69353`. errand-cloud accepts either name on inbound and always replies with the canonical, so the `_resolve_pending_response` waiter key now matches the response.
- **Use the canonical path in the cloud-proxy authorize redirect URL** returned to the browser, so errand-cloud sees the same provider name in the URL path as in the persisted state. The redirect URI registered with Google now includes the canonical callback path.
- **Update tests** that asserted on the legacy wire name + the old short-form OIDC scopes.
- **Bump VERSION** (patch).

## Capabilities

### Modified Capabilities

- `cloud-storage-oauth` — required scope list uses canonical OIDC URIs; WebSocket frames and cloud-proxy redirect path use the canonical Google provider name.

## Impact

- **Code**: `errand/integration_routes.py` — three small edits (scope list, two WebSocket sends, the redirect_url path).
- **Tests**: `errand/tests/test_integration_routes.py` — assert canonical wire name and canonical scopes.
- **DB**: existing `google_drive` PlatformCredential rows whose `granted_scopes` still contains the short `email`/`profile` from a pre-fix re-auth will continue to fail the per-scope check until the user re-authorises once. The next re-auth carries the canonical URIs and the warning clears for good. No migration needed.
- **Stale `google_workspace` row** persisted by older code (before `_handle_oauth_tokens` normalised) is invisible to the integration status endpoint and harmless. Cleaning it up is out of scope here.
- **External coordination**: requires the errand-cloud change `align-oidc-canonical-scopes` to ship together so both sides request the same canonical URIs.
