## Purpose

Registration and management of the errand instance's cloud-relay endpoint configuration, including subscription-error handling and webhook-endpoint registration with the cloud service.

## Requirements

### Requirement: Automatic endpoint registration with errand-cloud
The backend SHALL automatically register webhook endpoints with errand-cloud when both cloud credentials and Slack credentials are active.

#### Scenario: Cloud connected, Slack already enabled
- **WHEN** a user completes cloud authentication and Slack credentials exist with status "connected"
- **THEN** the backend SHALL call `POST /api/endpoints` on the cloud service with `{integration: "slack", label: "<instance-label>", signing_secret: "<slack-signing-secret>"}`
- **THEN** the backend SHALL store the returned endpoint URLs in the `cloud_endpoints` setting
- **THEN** the Authorization header SHALL use the cloud access token

#### Scenario: Slack enabled, cloud already connected
- **WHEN** a user saves Slack credentials and cloud PlatformCredential exists with status "connected"
- **THEN** the backend SHALL register cloud endpoints (same as above)

#### Scenario: Idempotent registration
- **WHEN** cloud endpoints for Slack already exist in the `cloud_endpoints` setting
- **THEN** the backend SHALL check `GET /api/endpoints?integration=slack` on the cloud service
- **THEN** if endpoints exist and are active, the backend SHALL NOT create duplicates
- **THEN** if no active endpoints exist (e.g., previously revoked), the backend SHALL create new ones

#### Scenario: Registration failure
- **WHEN** the cloud endpoint registration API call fails (network error, auth error, server error)
- **THEN** the backend SHALL log the error including the HTTP status code and response body
- **THEN** the backend SHALL store the error detail in the `cloud_endpoint_error` Setting
- **THEN** the backend SHALL NOT block the Slack credential save or cloud authentication flow
- **THEN** `GET /api/cloud/status` SHALL include `endpoint_error: {detail: "<message>"}` so the frontend can notify the user

#### Scenario: Registration succeeds after previous failure
- **WHEN** endpoint registration completes successfully
- **THEN** the backend SHALL delete the `cloud_endpoint_error` Setting if it exists

### Requirement: Endpoint cleanup on disconnect
When the user disconnects from errand-cloud, the backend SHALL revoke all cloud endpoints including webhook trigger endpoints for both Jira and GitHub.

#### Scenario: Disconnect revokes Slack endpoints
- **WHEN** the user disconnects from errand-cloud via the settings page
- **THEN** the backend SHALL call `DELETE /api/endpoints?integration=slack` on the cloud service
- **THEN** the backend SHALL delete the `cloud_endpoints` setting
- **THEN** the backend SHALL delete the `cloud_endpoint_error` setting

#### Scenario: Disconnect revokes Jira webhook trigger endpoints
- **WHEN** the user disconnects from errand-cloud via the settings page
- **THEN** the backend SHALL call `DELETE /api/endpoints?integration=jira` on the cloud service
- **THEN** the backend SHALL clear `cloud_webhook_url` and `cloud_endpoint_token` on all Jira webhook trigger records

#### Scenario: Disconnect revokes GitHub webhook trigger endpoints
- **WHEN** the user disconnects from errand-cloud via the settings page
- **THEN** the backend SHALL call `DELETE /api/endpoints?integration=github` on the cloud service
- **THEN** the backend SHALL clear `cloud_webhook_url` and `cloud_endpoint_token` on all GitHub webhook trigger records

#### Scenario: Endpoint cleanup failure
- **WHEN** the cloud endpoint revocation API call fails
- **THEN** the backend SHALL log the error but proceed with local cleanup (delete credentials and settings)

### Requirement: Webhook trigger endpoint registration with errand-cloud
The backend SHALL automatically register per-trigger webhook endpoints with errand-cloud when a webhook trigger is created or updated and the cloud connection is active. Registration SHALL be supported for both Jira (`integration="jira"`) and GitHub (`integration="github"`) triggers using the same wire shape. The returned per-trigger URL SHALL be stored on the trigger record so the UI can display it. Registration failures SHALL NOT block local trigger create/update/delete.

#### Scenario: Jira webhook trigger created with cloud connected
- **WHEN** a Jira webhook trigger is created and cloud PlatformCredential exists with status "connected"
- **THEN** the backend SHALL call `POST /api/endpoints` on the cloud service with `{integration: "jira", endpoint_type: "webhook", trigger_id: "<trigger-uuid>", webhook_secret: "<server-generated-secret>", label: "<trigger-name>"}`
- **THEN** the backend SHALL store the returned `url` field as `cloud_webhook_url` on the trigger record
- **THEN** the backend SHALL store the returned `token` field as `cloud_endpoint_token` on the trigger record

#### Scenario: GitHub webhook trigger created with cloud connected
- **WHEN** a GitHub webhook trigger is created and cloud PlatformCredential exists with status "connected"
- **THEN** the backend SHALL call `POST /api/endpoints` on the cloud service with `{integration: "github", endpoint_type: "webhook", trigger_id: "<trigger-uuid>", webhook_secret: "<server-generated-secret>", label: "<trigger-name>"}`
- **THEN** the backend SHALL store the returned `url` field as `cloud_webhook_url` on the trigger record
- **THEN** the backend SHALL store the returned `token` field as `cloud_endpoint_token` on the trigger record

#### Scenario: Server-generated webhook secret
- **WHEN** a webhook trigger is created
- **THEN** the backend SHALL generate the `webhook_secret` server-side using `secrets.token_urlsafe(32)`
- **THEN** the secret SHALL NOT be exposed to the user via any UI or API response
- **THEN** subsequent updates to the trigger SHALL preserve the existing secret (no regeneration)

#### Scenario: Webhook trigger updated
- **WHEN** a webhook trigger's name or filters are updated and cloud is connected
- **THEN** the backend SHALL re-call `POST /api/endpoints` with the same `trigger_id` and the existing `webhook_secret`
- **THEN** the cloud service SHALL upsert the existing endpoint matched by `trigger_id`
- **THEN** the returned URL and token SHALL replace the stored values on the trigger record

#### Scenario: Webhook trigger deleted with token known
- **WHEN** a webhook trigger is deleted, cloud is connected, and `cloud_endpoint_token` is populated
- **THEN** the backend SHALL call `DELETE /api/endpoints/{cloud_endpoint_token}` on the cloud service
- **THEN** the backend SHALL proceed with local deletion regardless of cloud API response

#### Scenario: Webhook trigger deleted with token unknown
- **WHEN** a webhook trigger is deleted, cloud is connected, and `cloud_endpoint_token` is null (registration never completed)
- **THEN** the backend SHALL call `DELETE /api/endpoints?integration={jira|github}&trigger_id=<trigger-uuid>` as a fallback
- **THEN** the backend SHALL proceed with local deletion regardless of cloud API response

#### Scenario: Cloud not connected when trigger created
- **WHEN** a webhook trigger is created but no cloud connection is active
- **THEN** the backend SHALL skip cloud registration and log a debug message
- **THEN** the trigger SHALL be created locally with `cloud_webhook_url` and `cloud_endpoint_token` set to null
- **THEN** registration SHALL be attempted by the reconciliation pass on the next cloud connect, or sooner if the trigger is updated

#### Scenario: Registration API call fails
- **WHEN** the `POST /api/endpoints` call fails (network error, HTTP 4xx other than 401, HTTP 5xx)
- **THEN** the backend SHALL log the error including HTTP status and response body
- **THEN** the trigger SHALL be created or updated locally
- **THEN** `cloud_webhook_url` and `cloud_endpoint_token` SHALL remain at their previous values (null on first failure, last-known values on subsequent failures)

#### Scenario: Registration API returns 403 (no active subscription)
- **WHEN** `POST /api/endpoints` returns HTTP 403 with detail "Active subscription required"
- **THEN** the backend SHALL log the condition at WARNING level
- **THEN** the trigger SHALL be created locally without cloud registration
- **THEN** the user SHALL be informed via the same `cloud_endpoint_error` Setting mechanism used for Slack registration failures

### Requirement: Webhook trigger endpoint reconciliation on cloud connect
On each successful cloud connect, the backend SHALL reconcile every Jira and GitHub webhook trigger against errand-cloud and re-register any whose endpoint no longer exists. Reconciliation SHALL reuse each trigger's stored webhook secret, so that a re-registered endpoint continues to verify deliveries signed with the secret already configured in the third-party system.

The local cache remains the display source. Reconciliation refreshes `cloud_webhook_url` and `cloud_endpoint_token`; it does not replace them with a live lookup at render time.

Reconciliation SHALL distinguish "errand-cloud reports the endpoint absent" from "errand-cloud could not be reached". Only the former may cause a stored URL to be discarded; an unreachable cloud SHALL leave the cache untouched.

Reconciliation SHALL NOT block or fail the cloud connect flow.

#### Scenario: Revoked endpoint is re-registered
- **WHEN** the backend connects to errand-cloud and a Jira or GitHub trigger's `cloud_endpoint_token` is absent from `GET /api/endpoints?integration=<source>`
- **THEN** the backend SHALL call `POST /api/endpoints` for that trigger with its existing `trigger_id` and stored webhook secret
- **THEN** the backend SHALL store the returned `url` and `token` on the trigger record
- **AND** the trigger's row in the Cloud Endpoints section SHALL show the new URL

#### Scenario: Live endpoint is left untouched
- **WHEN** a trigger's `cloud_endpoint_token` is present in the cloud listing
- **THEN** the backend SHALL NOT re-register that trigger
- **AND** `cloud_webhook_url` and `cloud_endpoint_token` SHALL be unchanged

#### Scenario: Never-registered trigger is registered on connect
- **WHEN** a trigger has `cloud_endpoint_token` set to null because registration was skipped or failed while the cloud was unavailable
- **THEN** reconciliation SHALL attempt registration for that trigger
- **AND** success SHALL populate `cloud_webhook_url` and `cloud_endpoint_token`

#### Scenario: Stored secret is reused, not regenerated
- **WHEN** a trigger is re-registered by reconciliation
- **THEN** the backend SHALL send the trigger's existing webhook secret
- **AND** SHALL NOT generate a new one, so that signature verification against the already-configured third-party webhook continues to succeed

#### Scenario: Endpoint is gone and re-registration fails
- **WHEN** errand-cloud reports a trigger's endpoint absent and the subsequent registration attempt fails
- **THEN** the backend SHALL clear `cloud_webhook_url` on that trigger
- **AND** the trigger's row SHALL display "Registration failed — re-save trigger to retry" rather than a URL that would silently drop deliveries
- **AND** the failure SHALL be recorded in the `cloud_endpoint_error` Setting, including when the cause is a webhook secret that cannot be decrypted or is empty (a null secret is instead generated and persisted by the existing backfill)

#### Scenario: Cloud unreachable during reconciliation
- **WHEN** the endpoint listing call fails with a network or server error
- **THEN** the backend SHALL NOT treat the result as "no endpoints exist"
- **AND** SHALL NOT re-register any trigger
- **AND** SHALL NOT clear any stored `cloud_webhook_url`

#### Scenario: Reconciliation failure does not break connect
- **WHEN** reconciliation raises at any point
- **THEN** the backend SHALL log the error
- **AND** the cloud connection SHALL complete normally

#### Scenario: One listing call per integration
- **WHEN** several Jira triggers exist
- **THEN** the backend SHALL issue a single `GET /api/endpoints?integration=jira` for the comparison
- **AND** SHALL NOT issue one request per trigger

#### Scenario: Reconnection reconciles too
- **WHEN** the cloud WebSocket client re-establishes a connection after a drop
- **THEN** reconciliation SHALL run for that connection as it does for a connection established at startup or by device authorization
- **AND** an endpoint revoked mid-session SHALL therefore be repaired on the next reconnect rather than waiting for a process restart

#### Scenario: Concurrent connects do not stack reconciliation passes
- **WHEN** a further cloud connect occurs while a reconciliation pass is still running
- **THEN** the backend SHALL suppress the duplicate pass rather than run both

#### Scenario: A burst of reconnects does not become a burst of requests
- **WHEN** the WebSocket reconnects repeatedly in quick succession
- **THEN** the backend SHALL run at most one pass per cooldown period, and SHALL NOT issue a listing call and registration attempt per reconnect
- **AND** a deliberate connect — process startup, or the user completing device authorization — SHALL run its pass regardless of the cooldown, since the user is waiting on the result

#### Scenario: A trigger deleted mid-pass is not re-created
- **WHEN** a webhook trigger is deleted after reconciliation read it but before it is re-registered
- **THEN** the backend SHALL NOT register an endpoint for that trigger
- **AND** reconciliation SHALL hold a per-trigger lock across re-reading the row, registering it, and persisting the result, so that a delete cannot interleave with those steps and leave an orphaned cloud endpoint

#### Scenario: A trigger that changes integration mid-pass is skipped
- **WHEN** a webhook trigger's source changes between reconciliation reading it and acting on it
- **THEN** the backend SHALL skip it rather than register it against the previous integration's listing

#### Scenario: A malformed endpoint listing is treated as a failure
- **WHEN** the endpoint listing call succeeds but the body is not a list of endpoint records
- **THEN** the backend SHALL treat the listing as failed
- **AND** SHALL NOT re-register any trigger or clear any stored URL

#### Scenario: An in-flight pass is cancelled on disconnect
- **WHEN** the user disconnects from errand-cloud while a reconciliation pass is running
- **THEN** the backend SHALL cancel that pass before revoking endpoints
- **AND** the pass SHALL NOT re-create an endpoint the disconnect has revoked
- **AND** every pass SHALL be cancellable, including those started by process startup and device authorization, not only those started by a WebSocket reconnect
- **AND** the WebSocket client SHALL be stopped before passes are cancelled, and cancellation SHALL account for a pass registered while cancellation is already under way

#### Scenario: Trigger create, update and delete re-read the row under the lock
- **WHEN** a trigger update or delete acquires the per-trigger lock
- **THEN** it SHALL re-read the row inside the lock before acting on the cloud
- **AND** an update SHALL skip cloud registration if the row has since been deleted, rather than re-creating an orphaned endpoint
- **AND** a delete SHALL revoke the token the row currently holds, not one a reconciliation pass has already replaced

#### Scenario: One trigger's failure does not end the pass
- **WHEN** reconciling one trigger raises
- **THEN** the backend SHALL log it and continue with the remaining triggers

#### Scenario: A replaced URL is reported to the user
- **WHEN** reconciliation re-registers a trigger that previously had a URL, and the new URL differs from it
- **THEN** the backend SHALL record the change, including the trigger's name, source, previous URL and new URL
- **AND** the record SHALL survive the intervening clearing of `cloud_webhook_url` by an earlier failed attempt, since the third-party system is still configured with the URL that was cleared
- **AND** repeated changes to the same trigger SHALL replace its record rather than accumulate

#### Scenario: A first registration is not a URL change
- **WHEN** reconciliation registers a trigger that had no URL and has never had one
- **THEN** the backend SHALL NOT record a change, because no third-party configuration exists to correct

#### Scenario: Recorded URL changes are dismissed by the user
- **WHEN** the user acknowledges the reported URL changes
- **THEN** the backend SHALL discard the records
- **AND** disconnecting from errand-cloud SHALL discard them too, alongside the other cached cloud state

#### Scenario: Reconciliation is skipped when cloud is not connected
- **WHEN** no cloud PlatformCredential exists, or its status is not "connected"
- **THEN** reconciliation SHALL NOT run
- **AND** SHALL NOT modify any trigger record
