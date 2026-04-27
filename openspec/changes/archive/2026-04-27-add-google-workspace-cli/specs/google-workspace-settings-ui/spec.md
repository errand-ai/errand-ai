## ADDED Requirements

### Requirement: Google Workspace section on Integrations page
The Settings → Integrations page SHALL display a "Google Workspace" section separate from the "Cloud Storage" section. This section SHALL show the Google Workspace connection status, the connected user's email and name (when connected), and a Connect or Disconnect button.

#### Scenario: Google Workspace not connected
- **WHEN** the Integrations page loads and no Google Workspace credentials exist
- **THEN** the Google Workspace section shows a "Connect" button
- **AND** the available services are listed but greyed out

#### Scenario: Google Workspace connected
- **WHEN** the Integrations page loads and Google Workspace credentials exist
- **THEN** the Google Workspace section shows the connected user's email and name
- **AND** a "Disconnect" button is displayed
- **AND** the available services are listed with active styling

#### Scenario: Re-authorization required
- **WHEN** the Integrations page loads and Google credentials have stale scopes (`reauth_required: true`)
- **THEN** the Google Workspace section shows a warning indicating expanded permissions are needed
- **AND** a "Re-authorize" button is displayed instead of "Disconnect"

### Requirement: Available services display
The Google Workspace section SHALL list the services available through the integration as informational badges or labels: Drive, Gmail, Calendar, Sheets, Docs, Chat, Tasks, Contacts.

#### Scenario: Services displayed as badges
- **WHEN** the Google Workspace section renders
- **THEN** service names are displayed as visual badges showing what the integration provides

#### Scenario: Services reflect connection state
- **WHEN** Google Workspace is connected
- **THEN** all service badges appear in an active/enabled style
- **WHEN** Google Workspace is not connected
- **THEN** all service badges appear in a muted/disabled style
