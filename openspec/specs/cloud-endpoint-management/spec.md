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
- **THEN** registration SHALL be attempted on the next trigger update (the user must re-save the trigger to retry — the system does NOT auto-backfill on cloud reconnect; per `design.md` "Backfilling existing triggers" is a non-goal)

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
