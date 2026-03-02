## Context

The errand-cloud relay requires an active subscription before endpoints can be registered. When a user connects to the cloud service but their subscription is missing or expired, `POST /api/endpoints` returns `403 {"detail":"Active subscription required"}`. The backend catches this exception and logs it, but the frontend is never notified — it remains stuck in a "Endpoints are being registered..." loading state indefinitely.

Additionally, users have no visibility into their subscription status or expiry date, making it impossible to self-diagnose the issue without checking logs.

Relevant code:
- `errand/cloud_endpoints.py` — registration and revocation; errors are swallowed
- `errand/main.py` → `GET /api/cloud/status` — does not include subscription info or endpoint errors
- `frontend/src/pages/settings/CloudServicePage.vue` — renders "Registering..." with no error path

## Goals / Non-Goals

**Goals:**
- Surface endpoint registration failures (including subscription errors) to the user via toast + clear UI state
- Display subscription expiry date on the cloud settings page
- Check subscription status proactively on page load (not only during registration)
- Replace the stuck "Registering..." message with an actionable error when registration fails

**Non-Goals:**
- Implementing subscription management or purchase flows
- Retrying failed endpoint registration automatically
- Changes to the errand-cloud service itself (this change is client-side only, treating `GET /api/subscription` as a cloud service contract)

## Decisions

### 1. Subscription data source: cloud service API, fetched at status check time

The cloud service is assumed to expose `GET /api/subscription` (Bearer auth, same access token) returning `{active: bool, expires_at: str | null}`. The backend fetches this when `GET /api/cloud/status` is called.

**Alternative considered:** Extract subscription info from JWT claims in the access token. Rejected — the token is opaque to clients and the cloud service may not embed subscription data in it; a dedicated API is the correct boundary.

**Alternative considered:** Store subscription info in the DB after fetching. Rejected — subscription status changes externally (expiry), so we should always fetch it fresh from the cloud service. If the call fails (network, 404 — cloud endpoint not yet implemented), the backend omits `subscription` from the status response and the frontend degrades gracefully.

### 2. Endpoint registration errors: stored in a Setting, included in cloud status response

When `POST /api/endpoints` fails, `try_register_endpoints` stores the error detail in a `cloud_endpoint_error` Setting (JSON: `{detail: str, timestamp: float}`). `GET /api/cloud/status` reads this setting and includes `endpoint_error: {detail: str}` in the response.

**Alternative considered:** Publish via SSE (`cloud_status` event). Rejected — the registration failure happens during the Slack credential save or OAuth callback, which are API calls, not WebSocket events. The frontend polls cloud status on page load; storing in DB and reading it there is simpler and doesn't require the frontend to maintain an SSE connection.

**Alternative considered:** Return the error from `PUT /api/platforms/slack/credentials` directly. Rejected — the registration is a best-effort side-effect of saving Slack credentials; mixing its failure into the credential save response conflates two concerns.

### 3. Error cleared on next successful registration

The `cloud_endpoint_error` setting is deleted when registration succeeds, and also cleared on disconnect. This keeps the stored state from going stale.

### 4. Frontend: toast on page load when endpoint_error is present

`CloudServicePage.vue` reads `endpoint_error` from the cloud status response and fires a toast notification on `onMounted`. The "Registering..." paragraph is replaced by an error paragraph when `endpoint_error` is set and `!hasEndpoints`.

## Risks / Trade-offs

- **`GET /api/subscription` may not exist yet** → Backend wraps the call in a try/except and omits `subscription` from the status response on failure. Frontend only shows expiry when the field is present. Zero breakage.
- **Stored `cloud_endpoint_error` can go stale** → We clear it on successful registration and disconnect; acceptable for an informational message.
- **Toast fires on every page load while error persists** → Toast is the correct UX for action-required messages; users will act on it (subscribe) or dismiss it. Not a regression.

## Migration Plan

No schema migrations needed (`cloud_endpoint_error` is a JSON Setting, using the existing Settings table). Deploy is a standard image bump.
