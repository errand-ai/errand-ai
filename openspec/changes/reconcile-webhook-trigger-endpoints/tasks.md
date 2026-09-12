## 1. Generalise the existing-endpoint check

- [ ] 1.1 Write a failing test that `check_existing_endpoints` can query an integration other than `slack`
- [ ] 1.2 Write a failing test that distinguishes "the cloud returned no endpoints" from "the call failed" — the current `except: return []` conflates them, and treating a failed call as "nothing exists" would re-register every trigger and change every URL
- [ ] 1.3 Add an `integration` parameter to `check_existing_endpoints` (`errand/cloud_endpoints.py:133`), defaulting to `slack` so existing callers are unchanged
- [ ] 1.4 Make failure distinguishable from emptiness — raise, or return `None` versus `[]` — and update the Slack caller to keep its current behaviour on failure
- [ ] 1.5 Confirm `try_register_endpoints` still behaves identically for Slack, including the previously-revoked re-create path

## 2. Reconciliation pass

- [ ] 2.1 Write a failing test: a Jira trigger whose `cloud_endpoint_token` is absent from the cloud listing is re-registered, and `cloud_webhook_url` / `cloud_endpoint_token` are updated to the new values
- [ ] 2.2 Write a failing test for the same with a GitHub trigger
- [ ] 2.3 Write a failing test that a trigger whose token IS present is left completely untouched — no POST, and the stored URL and token unchanged
- [ ] 2.4 Write a failing test that re-registration reuses the trigger's stored webhook secret rather than generating a new one
- [ ] 2.5 Add `reconcile_webhook_trigger_endpoints(session)` to `errand/cloud_endpoints.py`: resolve cloud context, list endpoints once per integration that has triggers, compare against stored tokens, re-register the missing
- [ ] 2.6 Handle a trigger with a null `cloud_endpoint_token` (registration never succeeded) — re-register it too, since reconnect is exactly when it can now succeed
- [ ] 2.7 Confirm one listing call per integration, not one per trigger

## 3. Failure handling

- [ ] 3.1 Write a failing test: the cloud says the endpoint is gone and re-registration returns 403, so `cloud_webhook_url` is cleared and the row falls back to "Registration failed — re-save trigger to retry"
- [ ] 3.2 Write a failing test: the listing call itself fails, so nothing is cleared and no URL is lost — this is the distinction from 1.2, at the level that matters to the user
- [ ] 3.3 Implement clearing only when the cloud affirmatively reports the endpoint absent and re-registration then fails
- [ ] 3.4 Write a test that an exception anywhere in reconciliation does not abort the cloud connect flow
- [ ] 3.5 Confirm the `cloud_endpoint_error` Setting is used consistently with existing registration failures, and that per-row text still excludes `endpoint_error.detail` as `cloud-settings-ui` requires

## 4. Wire into connect

- [ ] 4.1 Call reconciliation from the cloud connect path in `errand/main.py`, alongside `try_register_endpoints`
- [ ] 4.2 Confirm ordering and that neither pass depends on the other having run
- [ ] 4.3 Write a test that reconciliation does not run when cloud credentials are absent or not `connected`
- [ ] 4.4 Confirm the disconnect flow (`main.py:2243-2262`) is unaffected — it clears the local columns deliberately, and reconciliation must not undo that

## 5. Specs

- [ ] 5.1 Update `cloud-endpoint-management` — "Webhook trigger endpoint registration with errand-cloud": the "Cloud not connected when trigger created" scenario currently records auto-backfill as an explicit non-goal
- [ ] 5.2 Add the reconciliation requirement to `cloud-endpoint-management`
- [ ] 5.3 Update "Automatic endpoint registration with errand-cloud" if the generalised helper changes the Slack idempotency scenario's wording
- [ ] 5.4 Re-read `cloud-settings-ui` "Cloud endpoint URL display" and confirm no delta is needed — the failed-registration row is reused, not redefined

## 6. Verification

- [ ] 6.1 Confirm every test in sections 1-3 was demonstrated to fail before its fix
- [ ] 6.2 Run the full backend suite
- [ ] 6.3 Manually verify against the real defect: a trigger with a revoked cloud endpoint is repaired on reconnect, and its Cloud Endpoints row shows a new working URL
- [ ] 6.4 Verify the negative case by hand too — with the cloud unreachable, the page still shows cached URLs and clears nothing
