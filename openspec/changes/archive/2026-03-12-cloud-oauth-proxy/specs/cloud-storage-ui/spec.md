## MODIFIED Requirements

### Requirement: Cloud storage integration cards (MODIFIED)

The integration cards SHALL display a third visual state for providers that are unavailable because neither local credentials nor cloud service are configured.

#### Scenario: Provider available via cloud proxy
- **WHEN** the integration status API reports a provider with `mode: "cloud"`, `available: true`, `connected: false`
- **THEN** page displays the provider card with a "Connect" button (same as direct mode)
- **AND** clicking "Connect" navigates to the same `/api/integrations/{provider}/authorize` endpoint (the backend determines the flow)

#### Scenario: Provider unavailable — no credentials and no cloud
- **WHEN** the integration status API reports a provider with `mode: null`, `available: false`
- **THEN** page displays a greyed-out provider card
- **AND** shows message: "Configure Google/Microsoft credentials or connect to errand cloud to enable this integration"

#### Scenario: Connection detected via SSE event
- **WHEN** the cloud-proxy OAuth flow completes
- **AND** errand-server publishes a `cloud_storage_connected` event
- **THEN** the integration card updates to show the connected state without requiring a page refresh
