## MODIFIED Requirements

### Requirement: Cloud storage integration cards
The Cloud Storage section on the Integrations page SHALL display cards for OneDrive only. Google Drive is no longer part of the Cloud Storage section — it has moved to the Google Workspace section.

The integration cards SHALL display a third visual state for providers that are unavailable because neither local credentials nor cloud service is configured.

#### Scenario: OneDrive available via cloud proxy
- **WHEN** the integration status API reports OneDrive with `mode: "cloud"`, `available: true`, `connected: false`
- **THEN** page displays the OneDrive card with a "Connect" button

#### Scenario: OneDrive unavailable — no credentials and no cloud
- **WHEN** the integration status API reports OneDrive with `mode: null`, `available: false`
- **THEN** page displays a greyed-out OneDrive card
- **AND** shows message: "Configure Microsoft credentials or connect to errand cloud to enable this integration"

#### Scenario: OneDrive connection detected via SSE event
- **WHEN** the cloud-proxy OAuth flow completes for OneDrive
- **AND** errand-server publishes a `cloud_storage_connected` event
- **THEN** the OneDrive integration card updates to show the connected state without requiring a page refresh

#### Scenario: Cloud Storage section with only OneDrive
- **WHEN** the Integrations page renders
- **THEN** the Cloud Storage section displays only the OneDrive card
- **AND** Google Drive is NOT shown in the Cloud Storage section

## REMOVED Requirements

### Requirement: Google Drive integration card in Cloud Storage
**Reason**: Google Drive has moved to the new Google Workspace section which covers all Google services (Drive, Gmail, Calendar, etc.).
**Migration**: The Google Workspace section on the same Integrations page handles Google connection status.
