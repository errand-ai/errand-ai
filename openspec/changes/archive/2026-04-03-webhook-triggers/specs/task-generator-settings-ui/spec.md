## MODIFIED Requirements

### Requirement: Task Generators settings page
The application SHALL provide a "Task Generators" settings page at route `/settings/task-generators`. This page SHALL display trigger configurations that automatically create tasks. Each trigger type SHALL be displayed as a distinct card or section.

#### Scenario: Page accessible from settings navigation
- **WHEN** an admin clicks the "Task Generators" link in the settings sidebar
- **THEN** the page at `/settings/task-generators` loads and displays configured trigger types

#### Scenario: No triggers configured
- **WHEN** the Task Generators page loads and no triggers are configured
- **THEN** the page displays an empty state with guidance on available trigger types

### Requirement: Email trigger card
The Task Generators page SHALL display an "Email" trigger card when email platform credentials are configured. The card SHALL contain: an enable/disable toggle, a task profile selector dropdown, a poll interval input field (minimum 60 seconds), and a task prompt textarea.

#### Scenario: Email trigger card displayed
- **WHEN** the Task Generators page loads and email platform credentials exist
- **THEN** an "Email" trigger card is displayed with toggle, profile selector, poll interval, and task prompt fields

#### Scenario: Email trigger card hidden when no email credentials
- **WHEN** the Task Generators page loads and no email platform credentials exist
- **THEN** the Email trigger section shows a message directing the user to configure email credentials in Integrations first

#### Scenario: Enable/disable toggle
- **WHEN** an admin toggles the email trigger off
- **THEN** the email poller stops polling for new messages
- **AND** the toggle state is persisted

#### Scenario: Task profile selector
- **WHEN** the email trigger card renders
- **THEN** a dropdown populated from `GET /api/profiles` is displayed
- **AND** a "Default" option is available for when no specific profile is needed

#### Scenario: Poll interval validation
- **WHEN** an admin enters a poll interval below 60 seconds
- **THEN** the form shows a validation error indicating the minimum is 60 seconds

### Requirement: Task prompt field
The email trigger card SHALL include a "Task Prompt" textarea field. This prompt SHALL be appended to the task description when the email poller creates tasks, providing additional instructions for the LLM agent processing the email-triggered task.

#### Scenario: Task prompt saved
- **WHEN** an admin enters a task prompt and saves the email trigger settings
- **THEN** the task prompt is persisted and used for subsequent email-triggered tasks

#### Scenario: Task prompt empty
- **WHEN** the task prompt field is left empty
- **THEN** email-triggered tasks are created without additional prompt instructions (existing behavior)

#### Scenario: Task prompt used with Default profile
- **WHEN** an email trigger has no specific task profile selected but has a task prompt
- **THEN** email-triggered tasks use the Default profile and include the task prompt in the description

### Requirement: Webhook triggers section
The Task Generators page SHALL display a "Webhook Triggers" section below the email trigger section, showing a list of configured webhook triggers with add, edit, and delete capabilities.

#### Scenario: Webhook triggers section displayed
- **WHEN** the Task Generators page loads
- **THEN** a "Webhook Triggers" section is displayed below the email trigger card
- **THEN** each configured webhook trigger is shown as a row with its label, integration type, and status

#### Scenario: No webhook triggers configured
- **WHEN** the Task Generators page loads and no webhook triggers exist
- **THEN** the Webhook Triggers section displays an empty state with an "Add Webhook Trigger" button

#### Scenario: Add webhook trigger
- **WHEN** an admin clicks "Add Webhook Trigger"
- **THEN** a form is displayed with fields for label, integration type, task profile selector, task prompt, and a generated webhook secret
- **THEN** on save, the trigger is created via the backend API and the list refreshes

#### Scenario: Edit webhook trigger
- **WHEN** an admin clicks the edit button on a webhook trigger row
- **THEN** the form is populated with the trigger's current settings
- **THEN** the webhook secret is shown as masked (not editable) with an option to regenerate

#### Scenario: Delete webhook trigger
- **WHEN** an admin clicks the delete button on a webhook trigger row
- **THEN** a confirmation dialog is shown
- **THEN** on confirmation, the trigger is deleted via the backend API and the list refreshes

#### Scenario: Webhook URL display
- **WHEN** a webhook trigger has been registered with errand-cloud and has a cloud endpoint URL
- **THEN** the trigger row SHALL display the webhook URL with a copy button
- **THEN** the URL is the errand-cloud endpoint that external services (e.g., Jira) should be configured to POST to
