## MODIFIED Requirements

### Requirement: Cloud endpoint URL display
The Cloud Service settings page SHALL display the cloud webhook endpoint URLs when available, including per-trigger URLs for Jira and GitHub webhook triggers.

#### Scenario: Slack endpoints visible when Slack is enabled
- **WHEN** the user is connected to errand-cloud AND Slack credentials are configured
- **THEN** the page SHALL display a "Cloud Endpoints" section listing each Slack endpoint with its integration, type, and full URL
- **THEN** each endpoint URL SHALL have a "Copy" button to copy the URL to clipboard

#### Scenario: Per-trigger Jira and GitHub URLs visible
- **WHEN** the user is connected to errand-cloud AND one or more Jira or GitHub webhook triggers exist with `cloud_webhook_url` populated
- **THEN** the "Cloud Endpoints" section SHALL list each trigger's URL alongside the trigger's name and source (jira/github)
- **THEN** each URL SHALL have a "Copy" button to copy the URL to clipboard

#### Scenario: Trigger exists but cloud not connected
- **WHEN** a Jira or GitHub webhook trigger exists but `cloud_webhook_url` is null because the user is not connected to errand-cloud
- **THEN** the trigger's row in the "Cloud Endpoints" section SHALL display "Cloud not connected" in place of the URL
- **THEN** no "Copy" button SHALL be shown for that row

#### Scenario: Trigger exists but registration failed
- **WHEN** a Jira or GitHub webhook trigger exists, the user is connected to errand-cloud, but `cloud_webhook_url` is null because the most recent registration attempt failed
- **THEN** the trigger's row SHALL display "Registration failed — re-save trigger to retry"
- The per-row text SHALL NOT include `endpoint_error.detail` — that Setting is global (shared with Slack registration and other triggers) and would mis-attribute unrelated failures to the wrong trigger row. The detail SHALL be surfaced once at section level via the persistent endpoint-error banner instead.

#### Scenario: Endpoints hidden when no integrations are configured
- **WHEN** the user is connected to errand-cloud AND no Slack credentials, Jira triggers, or GitHub triggers exist
- **THEN** the "Cloud Endpoints" section SHALL NOT be displayed
- **THEN** a message SHALL indicate "Configure Slack, Jira, or GitHub in Integrations to see cloud webhook endpoints"

#### Scenario: Endpoint registration error
- **WHEN** the user is connected to errand-cloud AND the status response includes `endpoint_error`
- **THEN** the page SHALL display a toast notification on load with the error message (e.g. "Endpoint registration failed: Active subscription required")
- **THEN** the page SHALL display an inline error message in the Cloud Endpoints section for any endpoint that failed to register
- **THEN** the inline error SHALL include the `endpoint_error.detail` from the status response

#### Scenario: No Slack endpoints yet (no error)
- **WHEN** the user is connected to errand-cloud AND Slack credentials are configured AND no Slack endpoints are registered AND no `endpoint_error` is present
- **THEN** the page SHALL display a "Registering endpoints..." loading state for the Slack rows
