## ADDED Requirements

### Requirement: Cloud connection indicator in header
The app header SHALL display a cloud connection status indicator when the user has configured errand-cloud.

#### Scenario: Connected
- **WHEN** the cloud WebSocket connection is active
- **THEN** the header SHALL display a cloud icon with "Connected" text in green, positioned to the left of the version indicator

#### Scenario: Disconnected
- **WHEN** cloud credentials exist but the WebSocket connection is not active
- **THEN** the header SHALL display a cloud icon with "Disconnected" text in amber/yellow

#### Scenario: Not configured
- **WHEN** no cloud credentials exist
- **THEN** the cloud indicator SHALL NOT be displayed in the header

#### Scenario: Real-time updates
- **WHEN** the cloud connection status changes (connect, disconnect, error)
- **THEN** the header indicator SHALL update in real-time via `cloud_status` events received on the existing task events WebSocket
