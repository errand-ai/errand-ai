## Requirements

### Requirement: Project introspection API endpoint

The system SHALL expose a `POST /api/webhook-triggers/github/introspect-project` endpoint that accepts a JSON body with `org` (string) and `project_number` (integer). The endpoint SHALL use the stored GitHub platform credentials to query the GitHub GraphQL API and return the project's node ID, title, and Status field details (field ID and list of options with their IDs and names). The endpoint SHALL require admin role authorization.

#### Scenario: Successful project introspection

- **WHEN** a POST request is made with `{"org": "acme", "project_number": 5}` and valid GitHub credentials are stored
- **THEN** the response status is 200 and the body contains `{"project_node_id": "PVT_...", "title": "Platform Team", "status_field": {"field_id": "PVTSSF_...", "options": [{"id": "abc", "name": "Backlog"}, {"id": "def", "name": "Ready"}, ...]}}`

#### Scenario: No GitHub credentials configured

- **WHEN** the introspection endpoint is called but no GitHub platform credentials are stored
- **THEN** the response status is 400 with a message indicating GitHub credentials must be configured first

#### Scenario: Project not accessible

- **WHEN** the introspection endpoint is called with an org/project that the credentials cannot access
- **THEN** the response status is 400 with a message indicating the project was not found or is not accessible

### Requirement: GitHub trigger filter validation

When creating or updating a webhook trigger with `source: "github"`, the system SHALL validate that the `filters` dict contains the required keys: `project_node_id` (string, required), `trigger_column` (string, required). The optional key `content_types` (list of strings, values from `["Issue", "PullRequest", "DraftIssue"]`) SHALL default to `["Issue"]` if not provided. The system SHALL reject unknown filter keys for GitHub triggers.

#### Scenario: Valid GitHub trigger filters

- **WHEN** a trigger is created with `source: "github"` and `filters: {"project_node_id": "PVT_abc", "trigger_column": "Ready"}`
- **THEN** the trigger is created successfully

#### Scenario: Missing required filter key

- **WHEN** a trigger is created with `source: "github"` and `filters: {"project_node_id": "PVT_abc"}` (missing trigger_column)
- **THEN** the response status is 400 with a validation error

#### Scenario: Invalid content_types value

- **WHEN** a trigger is created with `filters: {"content_types": ["InvalidType"]}`
- **THEN** the response status is 400 with a validation error

### Requirement: GitHub trigger action validation

When creating or updating a webhook trigger with `source: "github"`, the system SHALL validate the `actions` dict for the following keys: `add_comment` (boolean), `comment_output` (boolean), `column_on_running` (string — column name), `column_on_complete` (string — column name), `copilot_review` (boolean), `review_profile_id` (UUID string — references a TaskProfile). The system SHALL also accept the cached project structure keys: `project_field_id` (string) and `column_options` (dict mapping column names to option IDs). The system SHALL reject unknown action keys for GitHub triggers.

#### Scenario: Valid GitHub trigger actions

- **WHEN** a trigger is created with `actions: {"add_comment": true, "column_on_running": "In Progress", "column_on_complete": "In Review", "copilot_review": true}`
- **THEN** the trigger is created successfully

#### Scenario: Review profile ID validated

- **WHEN** a trigger is created with `actions: {"review_profile_id": "uuid-value"}` and the UUID references an existing TaskProfile
- **THEN** the trigger is created successfully

#### Scenario: Review profile ID references non-existent profile

- **WHEN** a trigger is created with `actions: {"review_profile_id": "non-existent-uuid"}`
- **THEN** the response status is 400 with a validation error

### Requirement: Store cached project structure in trigger actions

When a trigger is created or updated with `source: "github"`, and the `actions` dict includes `column_on_running` or `column_on_complete`, the system SHALL resolve the column names to option IDs using the cached `column_options` mapping. If `column_options` is not present in the actions, the system SHALL perform a project introspection to populate it. The `project_field_id` and `column_options` keys SHALL be stored in the trigger's `actions` dict for use by the external status updater.

#### Scenario: Column options cached during trigger creation

- **WHEN** a trigger is created with `column_on_running: "In Progress"` and no `column_options` provided
- **THEN** the system introspects the project, caches the field ID and column options in the trigger's actions, and validates that "In Progress" exists as a column

#### Scenario: Column name not found in project

- **WHEN** a trigger is created with `column_on_running: "Nonexistent Column"` and the project does not have that column
- **THEN** the response status is 400 with a validation error indicating the column was not found

### Requirement: Frontend trigger configuration for GitHub Projects

The frontend SHALL provide a trigger configuration form for `source: "github"` that includes: a project URL or org/number input with an "Introspect" button that calls the introspection endpoint and populates column dropdowns, a trigger column selector (populated from introspected Status options), column mapping dropdowns for "on running" and "on complete" transitions, a Copilot review toggle, and an errand review task profile selector (populated from existing task profiles, shown when errand review is enabled). The form SHALL follow the existing webhook trigger settings UI patterns.

#### Scenario: User introspects project

- **WHEN** the user enters an org name and project number and clicks "Introspect"
- **THEN** the form populates the column dropdowns with the project's Status field options

#### Scenario: User configures review options

- **WHEN** the user enables "Copilot review" and selects a review task profile
- **THEN** the trigger actions include `copilot_review: true` and `review_profile_id: "<selected-uuid>"`

#### Scenario: Introspection fails

- **WHEN** the user clicks "Introspect" and the API returns an error
- **THEN** the form displays the error message and does not populate the dropdowns
