## Purpose

Frontend settings interface for managing webhook triggers, located on the Task Generators settings page alongside existing trigger sections.

## ADDED Requirements

### Requirement: Webhook triggers list
The settings page SHALL display a list of all configured webhook triggers showing each trigger's name, source type, enabled state (toggle), and associated profile name. The list SHALL include an "Add Trigger" button that opens the trigger creation form. Each trigger row SHALL be clickable to open the edit form for that trigger.

#### Scenario: Triggers displayed
- **WHEN** the user navigates to the Task Generators settings page and webhook triggers exist
- **THEN** all configured triggers are listed with their name, source, enabled toggle, and profile name

#### Scenario: No triggers configured
- **WHEN** the user navigates to the Task Generators settings page and no webhook triggers exist
- **THEN** an empty state message is shown with the "Add Trigger" button

#### Scenario: Toggle trigger enabled state
- **WHEN** the user toggles the enabled switch on a trigger in the list
- **THEN** the trigger's enabled state is updated via the API without opening the edit form

### Requirement: Trigger creation form
The trigger creation form SHALL include: a source selector dropdown (with "Jira" as an option and placeholder text for future sources), a name text input, an enabled toggle (default: on), source-specific filter configuration fields, actions configuration, a profile selector dropdown (populated from existing task profiles), a task prompt textarea, and a webhook secret field with a "Generate" button and option to paste a custom value. The form SHALL validate that name and profile are provided before allowing save.

#### Scenario: Create Jira trigger
- **WHEN** the user selects "Jira" as the source and fills in the name, selects a profile, and saves
- **THEN** a new webhook trigger is created via the API with the configured source, filters, actions, and profile

#### Scenario: Generate webhook secret
- **WHEN** the user clicks the "Generate" button on the webhook secret field
- **THEN** a cryptographically random secret is generated and displayed in the field

#### Scenario: Validation prevents save without required fields
- **WHEN** the user attempts to save a trigger without providing a name or selecting a profile
- **THEN** validation errors are shown on the missing fields and the save is blocked

### Requirement: Jira-specific filter configuration
When "Jira" is selected as the source, the form SHALL display: an event types multi-select with options including "jira:issue_created" and "jira:issue_updated", an issue types multi-select with common Jira issue types ("Task", "Story", "Bug", "Feature", "Epic"), a labels text input (comma-separated), and a projects text input (comma-separated project keys). All filter fields SHALL be optional; empty filters match all values.

#### Scenario: Configure event type filter
- **WHEN** the user selects "jira:issue_created" in the event types multi-select
- **THEN** the trigger's event_types filter is set to ["jira:issue_created"]

#### Scenario: Configure multiple filters
- **WHEN** the user selects issue types "Task" and "Bug", enters label "errand", and enters project "WEBAPP"
- **THEN** all filters are saved to the trigger configuration

#### Scenario: Leave filters empty
- **WHEN** the user creates a Jira trigger without selecting any filter values
- **THEN** the trigger is created with empty filter lists (matching all events, issue types, labels, and projects)

### Requirement: Actions configuration
The trigger form SHALL include an actions section with the following configurable options: a checkbox for "Assign to service account", a checkbox for "Add comment with task reference", a text input for "Add label" (the label value to add on completion), a text input for "Transition on complete" (the target transition name), and a checkbox for "Comment output on complete" (posts task output as a comment). Each action is independently toggleable.

#### Scenario: Configure completion actions
- **WHEN** the user enables "Transition on complete" and enters "Done" as the target transition
- **THEN** the trigger's actions include transition_on_complete with value "Done"

#### Scenario: No actions configured
- **WHEN** the user creates a trigger without enabling any actions
- **THEN** the trigger is created with no completion actions

#### Scenario: Multiple actions enabled
- **WHEN** the user enables "Add comment with task reference", "Add label" with value "errand-done", and "Comment output on complete"
- **THEN** all three actions are saved to the trigger configuration

### Requirement: Trigger edit form
The edit form SHALL load the existing trigger's configuration and populate all fields. The webhook secret field SHALL display the secret masked (e.g. "****...abcd") after initial save. The form SHALL include a "Delete" button that opens a confirmation dialog. All changes SHALL be saved via the API when the user clicks "Save".

#### Scenario: Edit existing trigger
- **WHEN** the user clicks on a trigger in the list
- **THEN** the edit form opens with all fields populated from the trigger's current configuration

#### Scenario: Webhook secret masked
- **WHEN** the edit form loads for a trigger with a saved webhook secret
- **THEN** the secret field displays a masked value and does not expose the full secret

#### Scenario: Update trigger configuration
- **WHEN** the user modifies the trigger name and saves
- **THEN** the updated configuration is sent to the API and the list reflects the change

### Requirement: Trigger detail view with webhook URL
The trigger detail view SHALL display the webhook URL that must be configured in the external system (e.g. Jira). The displayed URL SHALL be either the direct instance URL (e.g. `https://{instance}/api/webhooks/{trigger_id}`) or the cloud relay URL (e.g. `https://cloud.errand.ai/webhooks/{endpoint_id}`), depending on cloud connection status. The URL SHALL be displayed in a copyable field.

#### Scenario: Direct webhook URL displayed
- **WHEN** the user views a trigger detail and the instance is not connected to cloud
- **THEN** the direct webhook URL is displayed with a copy button

#### Scenario: Cloud relay URL displayed
- **WHEN** the user views a trigger detail and the instance is connected to cloud with an active endpoint
- **THEN** the cloud relay URL is displayed with a copy button

### Requirement: Delete trigger confirmation
The system SHALL display a confirmation dialog before deleting a webhook trigger. The dialog SHALL show the trigger name and warn that deletion is permanent and any webhooks configured in external systems will stop working.

#### Scenario: Confirm delete
- **WHEN** the user clicks "Delete" on a trigger and confirms the dialog
- **THEN** the trigger is deleted via the API and removed from the list

#### Scenario: Cancel delete
- **WHEN** the user clicks "Delete" on a trigger and cancels the dialog
- **THEN** the trigger is not deleted and the form remains open

### Requirement: Jira credential prerequisite
The webhook trigger settings page SHALL check whether Jira credentials are configured before allowing Jira trigger creation. If no Jira credentials exist (PlatformCredential with platform_id "jira" has status "disconnected" or does not exist), the system SHALL display a message directing the user to the Integrations settings page to configure Jira credentials. The "Add Trigger" button for Jira sources SHALL be disabled until Jira credentials are configured.

#### Scenario: Jira credentials not configured
- **WHEN** the user attempts to create a Jira trigger but no Jira credentials are stored
- **THEN** a message is displayed directing the user to configure Jira credentials on the Integrations page and the Jira source option is disabled

#### Scenario: Jira credentials configured
- **WHEN** the user opens the trigger creation form and Jira credentials exist with status "connected"
- **THEN** the Jira source option is available and selectable
