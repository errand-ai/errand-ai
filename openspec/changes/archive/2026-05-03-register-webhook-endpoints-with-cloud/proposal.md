## Why

Today the Jira and GitHub plugins in errand-server store credentials and trigger configuration locally but never tell errand-cloud about themselves. As a result:

1. **Cloud has no record of Jira/GitHub triggers** — the admin dashboard in errand-cloud reports zero Jira/GitHub endpoints for every tenant, even when the user has configured Jira credentials and triggers locally (verified against the devops-consultants production deployment via Loki: zero `GET /api/endpoints?integration=jira` or `?integration=github` requests in the past 30 days).
2. **The Cloud Service settings page has no URL to display** — there is currently no per-trigger webhook URL surfaced to the user, because errand-server never asked cloud for one and cloud never returned a per-tenant value anyway.
3. **No actual webhook deliveries from Jira/GitHub have ever reached cloud** — `POST /webhooks/jira` and `POST /webhooks/github` traffic in cloud is zero across the past 30 days, because users have nothing meaningful to configure in their Jira/GitHub project settings.

The companion change `unify-webhook-routing` in errand-cloud makes cloud return a per-trigger URL (`/hook/{token}`) on `POST /api/endpoints`. This change wires the Jira and GitHub plugins in errand-server to call that API, store the returned URL alongside the trigger, and display it on the Cloud Service settings page so the user can copy it into their Jira project / GitHub repo webhook configuration.

## What Changes

- Wire the **Jira plugin** to call `POST /api/endpoints` on errand-cloud whenever a Jira webhook trigger is created or updated:
  - Send `integration: "jira"`, `endpoint_type: "webhook"`, the `trigger_id`, a generated `webhook_secret`, and a human-readable `label`.
  - Store the returned `url` and `token` against the trigger in the local trigger model.
  - Re-call on trigger update (the cloud endpoint upserts on `trigger_id`).
  - Call `DELETE /api/endpoints/{token}` when the trigger is deleted.
- Wire the **GitHub plugin** identically (with `integration: "github"`).
- Display the per-trigger webhook URL on the **Cloud Service settings page** (`cloud-settings-ui`):
  - Show URL alongside each Jira trigger and each GitHub trigger.
  - Provide a copy-to-clipboard button.
  - Show a clear "Cloud not configured" or "Cloud not connected" state when there is no URL because the tenant has no cloud subscription or connectivity is broken.
- The webhook secret stored locally and sent to cloud SHALL be generated server-side (cryptographically random) and never editable by the user — it is a delivery-authentication detail, not a user-facing field.
- Auth for `POST /api/endpoints` reuses the existing trusted-auth bearer token already used by the Slack plugin (`cloud-trusted-auth` capability).

## Capabilities

### Modified Capabilities

- `cloud-endpoint-management`: SHALL handle Jira and GitHub webhook endpoint registration in addition to Slack. Each Jira/GitHub webhook trigger SHALL produce one POST/upsert call against cloud's `/api/endpoints` with `endpoint_type: "webhook"` and a per-trigger generated secret. Trigger deletion SHALL produce a corresponding DELETE.
- `jira-webhook-handler`: Trigger creation/update/deletion SHALL call cloud-endpoint-management to register, upsert, or revoke the corresponding cloud endpoint. The webhook secret SHALL be generated server-side and stored against the trigger.
- `github-webhook-handler`: Trigger creation/update/deletion SHALL call cloud-endpoint-management to register, upsert, or revoke the corresponding cloud endpoint. The webhook secret SHALL be generated server-side and stored against the trigger.
- `webhook-trigger-model`: Each Jira and GitHub trigger SHALL have a nullable `cloud_webhook_url` (string) and `cloud_endpoint_token` (string) field populated when registration with cloud succeeds, and cleared when the trigger is deleted.
- `webhook-trigger-settings-ui` (or `cloud-settings-ui` if URLs surface there instead): SHALL display the per-trigger cloud webhook URL with a copy-to-clipboard control, and SHALL show a clear placeholder when no URL is available (cloud not configured, not connected, or registration failed).

## Impact

- **errand-server backend**: Jira and GitHub plugin handlers extended to call cloud-endpoint-management on trigger create/update/delete. Local trigger model gains two columns (`cloud_webhook_url`, `cloud_endpoint_token`) — one Alembic-equivalent migration. Webhook secret generation centralised in a small helper.
- **errand-server frontend**: Settings page gains URL display + copy button per trigger. New "Cloud not configured" placeholder state.
- **errand-cloud**: This change depends on the cloud-side change `unify-webhook-routing` returning `/hook/{token}` URLs. With the cloud change shipped, this change becomes purely additive on the server side.
- **User experience**: First time a user configures a Jira or GitHub trigger after this ships, errand-server registers with cloud, gets back a URL, and shows it. The user copies that URL into their Jira project or GitHub repo webhook configuration. Real Jira/GitHub deliveries then start flowing through cloud → websocket → server.
- **Backfill**: Any existing Jira/GitHub triggers (none in production today) will not have a cloud URL until the user re-saves the trigger or a one-shot backfill job runs at startup. Recommend a startup backfill that walks existing triggers and registers any without a `cloud_endpoint_token` — keeps the user from having to touch each trigger manually.
- **Failure modes to handle**: cloud unreachable, cloud returns 4xx, tenant has no active subscription (cloud returns 403). In each case the trigger SHALL still be created locally; the URL field is populated on the next successful registration attempt (manual re-save or startup backfill).
