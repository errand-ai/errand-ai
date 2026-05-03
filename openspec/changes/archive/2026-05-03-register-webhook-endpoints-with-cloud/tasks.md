## 1. Data model

- [x] 1.1 Add `cloud_webhook_url: Mapped[str | None]` and `cloud_endpoint_token: Mapped[str | None]` columns to the `WebhookTrigger` SQLAlchemy model.
- [x] 1.2 Generate an Alembic migration adding both columns as nullable strings; verify reversibility with `alembic upgrade head` then `alembic downgrade -1`.
- [x] 1.3 Ensure `webhook_secret` is auto-populated on insert if not provided (server-generated via `secrets.token_urlsafe(32)`).

## 2. Cloud registration helper

- [x] 2.1 Add or extend a `register_webhook_trigger_with_cloud(trigger)` helper in the cloud-endpoint-management module that POSTs to `{cloud_base}/api/endpoints` with `{integration, endpoint_type: "webhook", trigger_id, webhook_secret, label}`.
- [x] 2.2 On 2xx response, store `url` → `trigger.cloud_webhook_url` and `token` → `trigger.cloud_endpoint_token` and commit.
- [x] 2.3 On non-2xx response, log the error, store the detail in `cloud_endpoint_error` Setting, and leave the trigger's cloud columns unchanged. Do not raise.
- [x] 2.4 Add `revoke_webhook_trigger_in_cloud(trigger)` helper that prefers `DELETE /api/endpoints/{trigger.cloud_endpoint_token}` when the token is set, falling back to `DELETE /api/endpoints?integration={source}&trigger_id={trigger.id}` otherwise.

## 3. Wire Jira and GitHub plugins

- [x] 3.1 In the Jira webhook trigger create/update handler, call `register_webhook_trigger_with_cloud` after the local commit succeeds.
- [x] 3.2 In the GitHub webhook trigger create/update handler, call `register_webhook_trigger_with_cloud` after the local commit succeeds.
- [x] 3.3 In the trigger delete handler (shared across sources), call `revoke_webhook_trigger_in_cloud` before the local delete.
- [x] 3.4 In the cloud disconnect handler, after revoking Slack endpoints, also call `DELETE /api/endpoints?integration=jira` and `DELETE /api/endpoints?integration=github`, then clear `cloud_webhook_url` and `cloud_endpoint_token` on all matching trigger rows.

## 4. UI changes

- [x] 4.1 Update the Cloud Service settings page to render Jira/GitHub trigger URLs alongside Slack URLs in the "Cloud Endpoints" section. Show "Cloud not connected" / "Registration failed" placeholders per the spec.
- [x] 4.2 Update the Trigger detail view to render `cloud_webhook_url` (when populated) with a Copy button. Replace any existing direct-URL fallback for cloud-connected instances with the cloud URL. Add the "Cloud not connected" / "Registering..." / "Retry" states described in the spec.
- [x] 4.3 Remove any user-facing webhook secret display (masked or otherwise) from the trigger edit form.

## 5. Tests

- [x] 5.1 Backend test: trigger create with cloud connected → cloud helper called with correct body; URL and token persisted.
- [x] 5.2 Backend test: trigger create with cloud disconnected → trigger persists with null cloud columns; helper not called.
- [x] 5.3 Backend test: trigger create with cloud returning 5xx → trigger persists; cloud columns null; error logged.
- [x] 5.4 Backend test: trigger update preserves the existing webhook_secret across re-registration calls.
- [x] 5.5 Backend test: trigger delete with token populated → uses `DELETE /api/endpoints/{token}`. With token null → uses bulk delete fallback.
- [x] 5.6 Backend test: cloud disconnect clears cloud columns on all trigger rows for jira and github sources.
- [x] 5.7 GitHub variant of all the above.
- [x] 5.8 Frontend component tests for the three Trigger detail view states (URL shown, "Cloud not connected", "Retry").

## 6. Verification

- [x] 6.1 Run backend test suite — all green.
- [x] 6.2 End-to-end smoke against a dev cloud: create a Jira trigger via the UI, confirm a `POST /api/endpoints` lands in cloud, the URL appears on the Cloud Service settings page, and a copy of that URL pasted into a Jira project webhook config delivers a test payload all the way to the connected websocket.
- [ ] 6.3 Repeat the smoke for GitHub.
- [ ] 6.4 Confirm the admin dashboard in errand-cloud now shows the new Jira/GitHub endpoints under the affected tenant.
