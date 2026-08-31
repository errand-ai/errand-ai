## Context

`cloud_auth_login` (`errand/main.py`) generates a CSRF nonce, stores it as the `cloud_auth_state` setting, and returns `{"redirect_url": "{cloud_url}/auth/tenant/login?redirect_uri={our callback}&state={nonce}"}`. `CloudServicePage.vue` opens that URL in a 500×600 popup via `window.open`. The user authenticates against the cloud's Keycloak, the cloud redirects back to `GET /api/cloud/auth/callback?code=…&state=…`, which validates the nonce, calls `exchange_code(cloud_url, code)` → `POST {cloud}/auth/tenant/token`, decodes `sub` and `email` from the access token, stores an encrypted `PlatformCredential`, starts the WebSocket client, registers cloud endpoints, and closes the popup with `window.close()`.

The `redirect_uri` in that first URL is this instance's own base URL. From errand-cloud's perspective it is a foreign origin, which is exactly what its origin check now refuses.

**The existing `cloud-auth` spec does not describe this.** It says the backend "SHALL generate a PKCE code_verifier and code_challenge" and "SHALL redirect to the Keycloak authorization endpoint". The implementation does neither — there is no PKCE anywhere in `cloud_auth_login`, and the redirect target is errand-cloud, not Keycloak. The spec appears to describe an earlier design that was superseded when the tenant-auth intermediary was introduced, and was never updated. Anyone reading it to understand the current flow would be misled, and a reviewer checking this change against it would compare against fiction. It is corrected here.

## Goals / Non-Goals

**Goals:**
- Obtain cloud tokens without sending errand-cloud any callback URL.
- Remove this instance as the reason the cloud's transitional override exists.
- Leave everything downstream of token acquisition untouched.
- Correct the `cloud-auth` spec to describe the flow that actually exists.

**Non-Goals:**
- Changing credential storage, encryption, refresh, WebSocket startup or endpoint registration.
- Forcing already-connected instances to re-authenticate.
- Anything on the errand-cloud side; that has shipped.

## Decisions

**Poll from the backend, not the browser.** The `device_code` is a bearer credential: whoever holds it collects the tokens when the grant is approved. Polling from `CloudServicePage.vue` would put it in the browser, where an XSS or a curious extension could take it, and would also mean the tokens arrive in the SPA and have to be posted back to be stored. Keeping the whole grant server-side means the browser only ever sees the `user_code` and the verification URL — neither of which is a credential, and both of which the user is meant to read aloud or retype anyway.

This costs a background task and a status endpoint the redirect flow did not need. That is the right trade: the redirect flow got its "server-side only" property for free because the browser was merely a courier between two servers, and the device grant has to buy the same property deliberately.

**Two endpoints, not one.** `POST /api/cloud/auth/device` starts the grant and returns the display fields; `GET /api/cloud/auth/device/status` reports `pending`, `connected`, `denied`, `expired` or `error`. The alternative — one endpoint that blocks until the grant resolves — would hold a request open for up to ten minutes, which is hostile to any proxy in front of this instance and gives the UI nothing to render meanwhile.

**Honour the advertised interval, and treat `slow_down` as authoritative.** errand-cloud returns `interval` (5 seconds) on initiation and answers `{"error": "slow_down"}` to a client polling faster. The poller uses the advertised interval rather than a hardcoded one, and on `slow_down` backs off by an additional 5 seconds per RFC 8628 §3.5 rather than retrying at the same rate. A poller that ignores this is indistinguishable from an abusive one, and the cloud rate limits these endpoints.

**One grant at a time.** Starting a second grant while one is pending abandons the first. The alternative — refusing while one is in flight — leaves a user who closed the tab stuck until the ten-minute expiry with no way to restart. Abandoning is safe because the device code lives only in this instance's memory and its cloud-side record expires on its own.

**Do not persist the device code.** It is short-lived and single-purpose, and writing it to the `Setting` table would put a bearer credential in the database in plaintext to no benefit. If the process restarts mid-grant the user starts again, which costs one click.

**Retire the callback rather than leave it inert.** `GET /api/cloud/auth/callback` and the `cloud_auth_state` setting have no role once nothing redirects here. Leaving a dead authenticated-adjacent endpoint on the surface is how the next reviewer finds something to worry about; deleting it is the honest end state. Existing rows for `cloud_auth_state` are dropped opportunistically on next login rather than by migration — the value is a nonce, so a stale one is inert.

## Risks / Trade-offs

- **The user must move to another surface to authorise** → A device grant is inherently two-surface. Mitigated by showing the verification URL as a link and the code in large type, and by `verification_uri_complete`, which carries the code in the query string so a click on the same machine needs no retyping.
- **Polling can leave a task running after the user gives up** → Bound the poller by the grant's own `expires_in` and stop on any terminal error. It must not outlive the grant.
- **The cloud rate limits the device endpoints** → Initiation is 10/min and polling 60/min per client IP. Honouring `interval` keeps a single grant at roughly 12 polls/min, within budget, but a retry storm from a buggy poller would trip it. The poller should surface a 429 as an error rather than tightening its loop.
- **The spec correction and the behaviour change land together** → A reviewer cannot diff the new spec against a truthful old one, because the old one was not truthful. The delta therefore states plainly what the previous requirements got wrong, rather than quietly replacing them.
- **This instance is the last holder of the cloud's override** → Until this ships, errand-cloud accepts an arbitrary `redirect_uri` from every tenant. That is the cost of sequencing and the reason this change should not sit.

## Migration Plan

No data migration. Connected instances keep their credentials and are unaffected; the change alters only how a *new* connection is established. Rollback is redeploying the previous image, which restores the redirect flow — and which still works only for as long as the cloud's override remains in place.

## Open Questions

- Should the verification code be shown alongside a QR code for the completion URL? Useful when the browser and the errand instance are on different machines; not required for correctness.
- Should a pending grant survive a backend restart? Deliberately not, above — worth revisiting if restarts during onboarding prove common.
