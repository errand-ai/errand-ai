## MODIFIED Requirements

### Requirement: Trigger detail view with webhook URL
The trigger detail view SHALL display the webhook URL that must be configured in the external system (e.g. Jira project, GitHub repository). When the instance is connected to errand-cloud and the trigger has a `cloud_webhook_url` populated, the cloud relay URL (`{cloud-base}/hook/{token}`) SHALL be displayed. When the instance is not connected to cloud or registration has not yet succeeded, a clear placeholder SHALL be shown instead. The URL SHALL be displayed in a copyable field with a "Copy" button.

#### Scenario: Cloud relay URL displayed
- **WHEN** the user views a trigger detail and the trigger's `cloud_webhook_url` is populated
- **THEN** the cloud relay URL SHALL be displayed with a "Copy" button
- **THEN** a hint SHALL indicate "Configure this URL in your Jira project / GitHub repository webhook settings"

#### Scenario: Cloud not connected
- **WHEN** the user views a trigger detail and the trigger's `cloud_webhook_url` is null because the instance is not connected to errand-cloud
- **THEN** the URL field SHALL display "Cloud not connected" with no Copy button
- **THEN** a link SHALL direct the user to the Cloud Service settings page to connect

#### Scenario: Registration did not complete
- **WHEN** the user views a trigger detail, the instance is connected to cloud, but `cloud_webhook_url` is null
- **THEN** the URL field SHALL display a message indicating registration with Errand Cloud did not complete and direct the user to the Cloud Service settings page for the error detail
- **THEN** a "Retry" button SHALL be available to re-trigger registration
- Note: registration is synchronous within the create/update request, so there is no separate "registering in progress" state — a null URL while cloud is connected always means the last attempt failed.

#### Scenario: Webhook secret not displayed
- **WHEN** the user views a trigger detail
- **THEN** the trigger's `webhook_secret` SHALL NOT be displayed in any form (masked or otherwise) — it is a server-internal value not relevant to the user
