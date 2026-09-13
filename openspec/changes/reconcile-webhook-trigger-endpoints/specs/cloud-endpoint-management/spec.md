## MODIFIED Requirements

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

## ADDED Requirements

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
- **AND** the failure SHALL be recorded in the `cloud_endpoint_error` Setting

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

#### Scenario: Reconciliation is skipped when cloud is not connected
- **WHEN** no cloud PlatformCredential exists, or its status is not "connected"
- **THEN** reconciliation SHALL NOT run
- **AND** SHALL NOT modify any trigger record
