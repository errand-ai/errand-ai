## Context

The `cloud-endpoint-management` capability already specifies that webhook trigger endpoints SHALL be registered with errand-cloud on trigger create/update/delete (`Webhook trigger endpoint registration with errand-cloud` requirement). However:

1. The existing requirement only covers Jira (`integration: "jira"`); GitHub triggers are not covered.
2. The wire shape it describes (`POST /api/endpoints` with `endpoint_type: "webhook"`, `trigger_id`, `webhook_secret`, `label`) returns a URL that — under the cloud's old contract — was a generic `/webhooks/jira` value, not a per-trigger URL. The companion errand-cloud change (`unify-webhook-routing`) makes that URL per-trigger (`/hook/{token}`), which is what makes the user-facing display meaningful.
3. **In practice the registration code path was never wired up** — Loki shows zero `GET /api/endpoints?integration=jira` or `?integration=github` requests across 30 days against the production cloud, and zero `POST /api/endpoints` calls for those integrations. The spec describes intent; the implementation never landed.

This change extends the spec to GitHub, makes the URL field name and storage explicit, and (most importantly) actually wires the calls.

The Cloud Service settings page currently has a `Cloud endpoint URL display` requirement that shows Slack URLs; this change extends it to also show per-trigger Jira/GitHub URLs.

## Goals / Non-Goals

**Goals:**
- Jira and GitHub plugins call `POST /api/endpoints` against cloud on trigger create/update, store the returned URL on the trigger row, and call `DELETE /api/endpoints/{token}` on trigger delete.
- Webhook secret is server-generated (cryptographically random), never user-editable.
- The per-trigger URL is shown on the Cloud Service settings page (or the Trigger detail view, whichever already shows trigger configuration) with a copy-to-clipboard control.
- The trigger model gains `cloud_webhook_url` and `cloud_endpoint_token` columns (nullable).
- Failure to reach cloud SHALL NOT block local trigger create/update/delete.

**Non-Goals:**
- Backfilling existing triggers. Per the user, no production triggers exist today; new triggers register on save.
- Changing how Jira/GitHub deliveries are *processed* once received (the existing `jira-webhook-handler` and `github-webhook-handler` capabilities are unchanged — they still parse and act on payloads the same way; only the *delivery transport* changes from "direct to errand-server" to "via cloud websocket").
- Moving the user-facing webhook URL display somewhere new. The existing `Trigger detail view with webhook URL` requirement and the `Cloud endpoint URL display` requirement already provide the homes; this change updates them to use the new per-trigger URL.
- Per-trigger label customisation in cloud beyond passing the trigger's name through.

## Decisions

### Decision: Server-generated webhook secret, never editable by the user

The webhook secret is purely a delivery-authentication detail between cloud and Jira/GitHub project settings. The user only needs the URL. Generating it server-side (32 bytes via `secrets.token_urlsafe(32)`) on trigger create simplifies the UI and prevents low-entropy secrets.

If the user re-saves a trigger, the secret is preserved (not regenerated) so that an already-configured Jira/GitHub webhook keeps working.

**Alternative considered:** allow the user to paste a secret. Rejected — it's noise in the UI and adds nothing for a value the user never needs to see.

### Decision: Two new nullable columns on the WebhookTrigger model

Add `cloud_webhook_url: str | None` and `cloud_endpoint_token: str | None` to `WebhookTrigger`. Both populated on successful registration with cloud, both null when registration hasn't happened yet (no cloud connection, registration failed, etc.).

The webhook secret stays on the trigger as `webhook_secret` (already exists) — this is what's sent to cloud at registration time.

**Alternative considered:** a separate `CloudEndpointRegistration` join table. Rejected — 1:1 with the trigger, no need for the indirection.

### Decision: Registration is best-effort; trigger creation never blocks on it

If `POST /api/endpoints` fails (network error, 4xx, 5xx, no cloud subscription), the trigger is still created locally. `cloud_webhook_url` stays null and the UI shows a "Cloud not configured" placeholder.

The user can fix the cloud connection and re-save the trigger to retry registration. No automatic retry loop in this change.

**Alternative considered:** background retry queue. Deferred — premature given there's nothing to retry today.

### Decision: Trigger delete revokes by token, not by trigger_id

The existing spec says `DELETE /api/endpoints?integration=jira&trigger_id=<uuid>` (via the bulk-delete endpoint). The cleaner per-token form `DELETE /api/endpoints/{token}` is preferred since we now store the token. Falls back to the bulk form if the token is missing (i.e. registration never completed).

### Decision: GitHub mirrors Jira exactly

Same wire shape (`{integration: "github", endpoint_type: "webhook", trigger_id, webhook_secret, label}`), same handlers, same UI. Symmetry > minimal duplication.

## Risks / Trade-offs

| Risk | Mitigation |
|---|---|
| User saves a trigger while cloud is down → empty URL → confusion | UI shows an explicit "Cloud not connected — save trigger again to register" placeholder. |
| Webhook secret stored in two places (server DB + cloud DB) drifts | Always upsert via `trigger_id` from the server side; cloud is the relay, server is the source of truth. |
| User deletes a trigger, cloud DELETE fails → orphan endpoint in cloud | Log + carry on; the orphan endpoint is harmless (no inbound traffic ever matches a deleted local trigger). A periodic reconciliation job is out of scope. |
| GitHub plugin doesn't yet emit a `trigger_id` per webhook config | Verify in implementation; if it doesn't, generate one on first registration and persist it. |

## Migration Plan

1. Ship the cloud-side `unify-webhook-routing` change first (cloud must return `/hook/{token}` URLs).
2. Ship this change. New Jira/GitHub triggers register on save.
3. No backfill — there are no existing triggers in production today.

## Open Questions

None outstanding.
