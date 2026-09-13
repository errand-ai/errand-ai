## Why

Slack endpoints repair themselves after a cloud-side revocation. Jira and GitHub trigger endpoints never do, and the settings page cannot tell the difference — it shows a dead URL exactly as it shows a live one.

`try_register_endpoints` runs on every cloud connect, calls `check_existing_endpoints`, and re-creates Slack endpoints if the cloud no longer has any. Webhook trigger endpoints are registered once, when the trigger is saved, and are never checked again. `check_existing_endpoints` (`errand/cloud_endpoints.py:143`) hardcodes `?integration=slack`, so it could not see them even if it were asked to.

The consequence is visible in production. Tenant `0dd9ea65…` on errand-cloud holds 45 endpoint records, 3 active. Its Slack and Jira endpoints were created together on 2026-05-18 and revoked together by an errand-cloud defect; on 2026-06-07 the three Slack endpoints came back and the Jira one did not. The Cloud Service settings page has been displaying that Jira URL, with a working Copy button, ever since — while `/hook/<token>` has been rejecting deliveries the whole time, because errand-cloud's lookup filters on `revoked_at IS NULL`.

Two views disagreed with no way to tell which was right: errand-cloud's account page listed three endpoints, the desktop listed four, and nothing on either screen indicated staleness.

This reverses a decision recorded in the current spec, which states that the system "does NOT auto-backfill on cloud reconnect" and that the user must re-save the trigger to retry. That decision assumed a failed registration was the only way a trigger could lack a live endpoint, and that the user would know it had happened. Neither holds: the endpoint can be revoked server-side long after a successful registration, and the UI actively conceals it.

The cloud-side defect is fixed separately (`errand-cloud`: `revoke-endpoints-only-on-access-loss`). This change makes the desktop resilient to it recurring, for any reason.

## What Changes

- **Reconcile webhook trigger endpoints on cloud connect.** For each Jira and GitHub trigger, verify the stored `cloud_endpoint_token` is still active on errand-cloud, and re-register any that are missing or revoked, reusing the trigger's existing webhook secret so the URL is the only thing that changes.
- **Generalise the existence check.** `check_existing_endpoints` takes an integration rather than assuming Slack, so the same helper serves both paths.
- **The local cache stays.** `cloud_endpoints` and `cloud_webhook_url` remain the display source, so the page still renders offline. Reconciliation refreshes the cache; it does not replace it.
- **Stop showing dead URLs as live.** When reconciliation determines an endpoint is gone and cannot re-register it, clear `cloud_webhook_url` so the existing "Registration failed — re-save trigger to retry" row is shown instead of a URL that will silently drop deliveries.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `cloud-endpoint-management`: add reconciliation of webhook trigger endpoints on cloud connect; generalise the existing-endpoint check beyond Slack; reverse the recorded non-goal that the system does not backfill on reconnect.

`cloud-settings-ui` needs **no** delta. "Cloud endpoint URL display" already specifies the "Registration failed — re-save trigger to retry" row for a trigger whose `cloud_webhook_url` is null while connected. Reconciliation reuses that state rather than introducing a new one.

## Impact

- `errand/cloud_endpoints.py` — generalise `check_existing_endpoints`; add the reconciliation pass.
- `errand/main.py` — invoke reconciliation on the cloud connect path, alongside `try_register_endpoints`.
- `errand/tests/test_cloud_endpoints.py` — reconciliation coverage.

**Recovery is not immediate.** Reconciliation runs on connect, so an endpoint revoked mid-session stays stale until the next reconnect. Given the WebSocket reconnects frequently this is a short window in practice, but it is a window, and it is why the stale-URL display fix matters independently of the reconciliation.

**The URL changes.** A re-registered trigger gets a new token and therefore a new URL, which the user must paste into Jira or GitHub again. Reconciliation restores the endpoint; it cannot restore the third-party configuration pointing at the old one.

**Out of scope:** the errand-cloud revocation bug; reconciling Slack endpoints, which already works; any change to how webhook secrets are generated or stored.
