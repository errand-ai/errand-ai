## ADDED Requirements

### Requirement: Cloud storage integration cards

The Settings > Integrations page SHALL display integration cards for Google Drive and OneDrive, showing connection status and providing connect/disconnect actions.

#### Scenario: Provider available and not connected
- **WHEN** user views the Integrations page
- **AND** the integration status API reports Google Drive as `available: true, connected: false`
- **THEN** page displays a Google Drive card with a "Connect" button

#### Scenario: Provider available and connected
- **WHEN** the integration status API reports Google Drive as `available: true, connected: true`
- **THEN** page displays a Google Drive card showing the connected user email/name and a "Disconnect" button

#### Scenario: Provider not available
- **WHEN** the integration status API reports OneDrive as `available: false`
- **THEN** page displays a greyed-out OneDrive card with a message indicating the MCP server is not configured

### Requirement: Connect action triggers OAuth redirect

When the user clicks "Connect" on a cloud storage integration card, the frontend SHALL redirect the browser to the backend's OAuth authorize endpoint for that provider.

#### Scenario: User clicks Connect on Google Drive
- **WHEN** user clicks "Connect" on the Google Drive card
- **THEN** browser navigates to `/api/integrations/google_drive/authorize`
- **AND** the OAuth flow proceeds through Google's consent screen
- **AND** user is redirected back to the Integrations page after completion

### Requirement: Disconnect action removes credentials

When the user clicks "Disconnect" on a connected cloud storage integration card, the frontend SHALL call the disconnect endpoint and refresh the integration status.

#### Scenario: User disconnects OneDrive
- **WHEN** user clicks "Disconnect" on the OneDrive card
- **THEN** frontend sends `DELETE /api/integrations/onedrive`
- **AND** refreshes integration status
- **AND** card updates to show "Connect" button
