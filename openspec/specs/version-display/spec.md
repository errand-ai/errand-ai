## Purpose

Frontend header component displaying the deployed version with an update-available indicator.

## Requirements

### Requirement: Version displayed in header
The frontend header SHALL display the current deployed version as text, positioned to the left of the GitHub link in the header's right-aligned section. The version SHALL be prefixed with `v` (e.g., `v0.65.0`). The text SHALL use a muted style consistent with the existing GitHub link.

#### Scenario: Version shown on page load
- **WHEN** the page loads and `/api/version` returns `{"current": "0.65.0", "latest": "0.65.0", "update_available": false}`
- **THEN** the header displays `v0.65.0` to the left of the GitHub link

#### Scenario: PR version shown
- **WHEN** `/api/version` returns `{"current": "0.65.0-pr66", ...}`
- **THEN** the header displays `v0.65.0-pr66`

#### Scenario: Dev version shown
- **WHEN** `/api/version` returns `{"current": "dev", ...}`
- **THEN** the header displays `dev` (no `v` prefix for non-semver versions)

### Requirement: Update available indicator
When a newer version is available, the frontend SHALL display a small colored dot indicator adjacent to the version text. The dot SHALL have a tooltip that shows the available version (e.g., `v0.66.0 available`).

#### Scenario: Update available
- **WHEN** `/api/version` returns `{"current": "0.65.0", "latest": "0.66.0", "update_available": true}`
- **THEN** a colored dot appears next to the version text with a tooltip reading `v0.66.0 available`

#### Scenario: No update available
- **WHEN** `/api/version` returns `{"update_available": false}`
- **THEN** no dot indicator is displayed

#### Scenario: Latest unknown
- **WHEN** `/api/version` returns `{"latest": null, "update_available": false}`
- **THEN** no dot indicator is displayed

### Requirement: Version fetched on page load
The frontend SHALL fetch `/api/version` when the application mounts. If the fetch fails, the version area SHALL be hidden (no error shown to the user).

#### Scenario: Fetch succeeds
- **WHEN** the app mounts and `/api/version` returns successfully
- **THEN** the version and update indicator are displayed

#### Scenario: Fetch fails
- **WHEN** the app mounts and `/api/version` returns an error or times out
- **THEN** no version information is displayed in the header
