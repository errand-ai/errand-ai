## Purpose

Settings → Integrations → "Google Workspace" section UI. Replaces the old "Google Drive" card under "Cloud Storage" with a dedicated section that surfaces all of the services covered by the gws CLI (Drive, Gmail, Calendar, Sheets, Docs, Chat, Tasks, Contacts) and a Re-authorize affordance for stale-scope tokens.

## Requirements

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
The Google Workspace section SHALL list the services available through the integration as service badges (Drive, Gmail, Calendar, Sheets, Docs, Chat, Tasks, Contacts). Each badge's active styling SHALL be driven by the presence of one of that service's required OAuth scopes in the `granted_scopes` list returned by the integration status endpoint, NOT by a single connected/disconnected boolean — so partial-grant states render correctly.

The badge → scope mapping SHALL be:

| Badge | Required scope (any of) |
|-------|------------------------|
| Drive | `https://www.googleapis.com/auth/drive` |
| Gmail | `https://www.googleapis.com/auth/gmail.modify`, `https://www.googleapis.com/auth/gmail.send` |
| Calendar | `https://www.googleapis.com/auth/calendar` |
| Sheets | `https://www.googleapis.com/auth/spreadsheets` |
| Docs | `https://www.googleapis.com/auth/documents` |
| Chat | `https://www.googleapis.com/auth/chat.messages` |
| Tasks | `https://www.googleapis.com/auth/tasks` |
| Contacts | `https://www.googleapis.com/auth/contacts`, `https://www.googleapis.com/auth/contacts.readonly` |

The *"Expanded permissions are required"* warning + **Re-authorize** affordance SHALL be visible if AND ONLY IF the user is connected AND at least one badge's required scope is missing from the granted set (i.e. broaden the existing `reauth_required` boolean to also catch partial-grant states).

#### Scenario: Services displayed as badges
- **WHEN** the Google Workspace section renders
- **THEN** service names are displayed as visual badges showing what the integration provides

#### Scenario: Full Workspace scope set granted
- **WHEN** the integration status carries every required scope listed above
- **THEN** every badge renders in the active style
- **AND** the warning is NOT visible
- **AND** a "Disconnect" button is displayed

#### Scenario: Drive-only legacy token
- **WHEN** the integration status carries only `https://www.googleapis.com/auth/drive`
- **THEN** the Drive badge renders in the active style
- **AND** every other Workspace badge renders in the muted/disabled style
- **AND** the warning + Re-authorize button are visible

#### Scenario: Partial grant
- **WHEN** the integration status carries `auth/drive`, `auth/gmail.modify`, and `auth/calendar` but no other Workspace scopes
- **THEN** the Drive, Gmail, and Calendar badges render in the active style
- **AND** Sheets, Docs, Chat, Tasks, Contacts render in the muted/disabled style
- **AND** the warning + Re-authorize button are visible

#### Scenario: Not connected
- **WHEN** no Google Workspace credentials exist
- **THEN** every badge renders in the muted/disabled style
- **AND** a "Connect" button is displayed
