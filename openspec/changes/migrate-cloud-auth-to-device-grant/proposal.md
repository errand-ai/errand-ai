## Why

errand-cloud has removed the redirect path this instance authenticates with. Its `harden-auth-and-public-endpoints` change (errand-ai/errand-cloud#73, deployed as `0.31.0-pr73.371`) closed a Critical finding: `GET /auth/tenant/login` accepted any `redirect_uri` and the callback appended the freshly minted authorization code to it, so an attacker who started the flow with their own `redirect_uri` and induced a victim through it received a credential exchangeable for access and refresh tokens. That is account takeover, not the open redirect it was first recorded as.

The parameter could not be validated. A registry of permitted redirect origins cannot be maintained for an open population of self-hosted instances on URLs the cloud's operators neither control nor know — an objection that change inherited from the archived `add-tenant-auth-flow` design and upheld. So the cloud removed the parameter instead, adding an OAuth 2.0 device authorization grant (RFC 8628) for self-hosted instances and keeping the redirect flow only for its own SPA, constrained to its own origin.

**This instance is why the vulnerability is still open in production.** `cloud_auth_login` builds `{cloud_url}/auth/tenant/login?redirect_uri={our own callback}` (`errand/main.py:1789`), which the cloud's origin check refuses with HTTP 400. When the cloud deployed, that broke this instance's login until a transitional override — `TENANT_LOGIN_ALLOW_FOREIGN_REDIRECT`, set in the deployment's ArgoCD values — restored the permissive behaviour.

That override is not scoped to this instance. While it is set, errand-cloud accepts an arbitrary `redirect_uri` from *anyone*, so the account-takeover path is open for every tenant of the service. The cloud logs a warning on each use, but the exposure is real and it persists until this change lands. **This change is what actually closes S1 in production**, and it is the sole remaining blocker on tasks 1.11 and 1.12 of the cloud's change.

## What Changes

- **Replace the redirect-based cloud login with the device authorization grant.** The backend requests a device code from errand-cloud, shows the user a short verification code and a URL on the cloud's own origin, and polls for tokens. No callback URL is sent, so there is nothing for the cloud to verify and nothing for an attacker to substitute.
- **Retire `GET /api/cloud/auth/callback` and the `cloud_auth_state` nonce.** Neither has a role once no redirect returns to this instance.
- **Replace the popup in `CloudServicePage.vue`** with an in-page panel showing the verification code and link, and a status that resolves when the backend completes the grant.
- **Credential storage, refresh, WebSocket startup and endpoint registration are unchanged.** The grant yields the same Keycloak tokens through the same `POST /auth/tenant/token`-equivalent exchange, so everything downstream of "we have tokens" keeps working.

## Capabilities

### Modified Capabilities

- `cloud-auth`: replace the authorization-code-via-redirect requirements with device-grant requirements. Note the existing spec is **already inaccurate** — it describes a PKCE flow conducted directly against Keycloak, while the implementation has always gone through errand-cloud's `/auth/tenant/login`. That drift is corrected as part of this change rather than carried forward.

## Impact

- `errand/cloud_auth.py` — add device-code initiation and polling; `exchange_code` becomes unused.
- `errand/main.py` — replace `cloud_auth_login`, retire `cloud_auth_callback`, drop the `cloud_auth_state` setting.
- `frontend/src/pages/settings/CloudServicePage.vue` — replace the popup with the verification-code panel.
- `openspec/specs/cloud-auth/spec.md` — via the delta.

**Coordination.** errand-cloud's device endpoints are already deployed, so this side can be built and tested against the live service immediately. Once this instance authenticates by device grant, the `tenantAuth.allowForeignRedirect: true` block must be deleted from `errand-cloud-values.yaml` in `devops-consultants/argocd` — that deletion is task 1.12 of the cloud's change and is what finally closes S1.

**No data migration.** Existing cloud credentials keep working; this changes only how new ones are obtained. A connected instance is not forced to re-authenticate.

**Out of scope:** the cloud's own SPA login, the telemetry token scheme, and the rate limiting introduced alongside the device grant. All are errand-cloud's side and already shipped.
