## MODIFIED Requirements

### Requirement: Platform credential configuration form

Each platform card SHALL have a "Configure" button that expands an inline form. The form fields SHALL be dynamically rendered from the platform's `credential_schema` (fetched from `GET /api/platforms`). Supported field types: `password` (masked input with reveal toggle), `text` (plain text input), `textarea` (multi-line text input), `select` (pill-button toggle with options), and `profile_select` (dropdown populated from `GET /api/profiles`). The form SHALL have "Test & Save" and "Cancel" buttons.

#### Scenario: Configure Twitter credentials

- **WHEN** an admin clicks "Configure" on the Twitter card
- **THEN** a form appears with masked input fields for API Key, API Secret, Access Token, and Access Secret (as defined by Twitter's credential_schema)

#### Scenario: Configure email credentials with profile selector

- **WHEN** an admin clicks "Configure" on the Email card
- **THEN** a form appears with text inputs for IMAP/SMTP settings, a security mode toggle, a password field, a task profile dropdown, a poll interval field, and an authorised recipients textarea

#### Scenario: Save credentials

- **WHEN** an admin fills in all credential fields and clicks "Test & Save"
- **THEN** the frontend sends `PUT /api/platforms/email/credentials` with the field values and displays the result (connected or error message)

#### Scenario: Cancel editing

- **WHEN** an admin clicks "Cancel" on an open credential form
- **THEN** the form collapses and no changes are saved
