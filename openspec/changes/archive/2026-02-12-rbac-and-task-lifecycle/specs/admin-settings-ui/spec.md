## MODIFIED Requirements

### Requirement: Settings page layout

_(Append to existing requirement — archive after setting)_

The Settings page SHALL display an additional section "Task Archiving" containing a number input labelled "Archive after (days)" for configuring how many days completed tasks remain on the board before being auto-archived. The input SHALL load its current value from `GET /api/settings` (key `archive_after_days`). If no `archive_after_days` setting exists, the input SHALL default to `3`. A "Save" button SHALL send the updated value via `PUT /api/settings` with `{"archive_after_days": <number>}`.

#### Scenario: Load default archive interval
- **WHEN** the Settings page loads and no `archive_after_days` setting exists
- **THEN** the "Archive after (days)" input displays `3`

#### Scenario: Load existing archive interval
- **WHEN** the Settings page loads and `archive_after_days` is set to `7`
- **THEN** the "Archive after (days)" input displays `7`

#### Scenario: Save archive interval
- **WHEN** the admin changes the archive interval to `5` and clicks "Save"
- **THEN** the frontend sends `PUT /api/settings` with `{"archive_after_days": 5}` and displays a success indication

### Requirement: Archived Tasks navigation link

The header user dropdown SHALL include an "Archived Tasks" link that navigates to `/archived`. The link SHALL be visible to all authenticated users (viewer, editor, admin), positioned above the Settings link in the dropdown.

#### Scenario: Viewer sees Archived Tasks link
- **WHEN** a viewer opens the user dropdown in the header
- **THEN** the dropdown includes an "Archived Tasks" link but not a "Settings" link

#### Scenario: Admin sees both links
- **WHEN** an admin opens the user dropdown in the header
- **THEN** the dropdown includes both "Archived Tasks" and "Settings" links

#### Scenario: Archived Tasks link navigates to page
- **WHEN** a user clicks the "Archived Tasks" link in the dropdown
- **THEN** the browser navigates to `/archived`
