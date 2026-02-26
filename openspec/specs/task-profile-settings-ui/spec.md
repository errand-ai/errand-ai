## ADDED Requirements

### Requirement: Task Profiles settings sub-page
The frontend SHALL have a "Task Profiles" settings sub-page at `/settings/profiles`. The page SHALL display a list of all custom task profiles with their name, description, model override, and tool selection summary. Each profile SHALL have Edit and Delete actions.

#### Scenario: Page displays profiles
- **WHEN** an admin navigates to `/settings/profiles` with 2 profiles defined
- **THEN** the page shows 2 profile cards with name, description, model, and tool summary

#### Scenario: Page displays empty state
- **WHEN** an admin navigates to `/settings/profiles` with no profiles defined
- **THEN** the page shows an empty state message and an "Add Profile" button

### Requirement: Add Profile button and form
The page SHALL have an "Add Profile" button that opens a form (modal or inline) for creating a new task profile. The form SHALL include fields for: name (text input), description (text input), match rules (textarea), model (dropdown or blank to inherit), system prompt (textarea or blank to inherit), max turns (number input or blank to inherit), reasoning effort (dropdown: low/medium/high or blank to inherit), MCP servers (selection), LiteLLM MCP servers (selection), and skills (selection).

#### Scenario: Create a profile
- **WHEN** an admin fills in the form with name "email-triage", model "claude-haiku-4-5-20251001", and clicks Save
- **THEN** `POST /api/task-profiles` is called and the new profile appears in the list

#### Scenario: Validation error on duplicate name
- **WHEN** an admin tries to create a profile with a name that already exists
- **THEN** an error toast is shown with the conflict message

### Requirement: List field selection UI
For MCP servers, LiteLLM MCP servers, and skills, the form SHALL provide a three-state selection: "Inherit from default" (saves null), "None" (saves empty array), or "Select specific" (saves the selected items as an array). The "Select specific" option SHALL show checkboxes for available items.

#### Scenario: Inherit from default selected
- **WHEN** an admin selects "Inherit from default" for MCP servers
- **THEN** the profile is saved with `mcp_servers: null`

#### Scenario: None selected
- **WHEN** an admin selects "None" for MCP servers
- **THEN** the profile is saved with `mcp_servers: []`

#### Scenario: Specific items selected
- **WHEN** an admin selects "Select specific" and checks "gmail" and "errand"
- **THEN** the profile is saved with `mcp_servers: ["gmail", "errand"]`

### Requirement: Edit profile
Clicking Edit on a profile SHALL open the form pre-populated with the profile's current values. Saving SHALL call `PUT /api/task-profiles/{id}`.

#### Scenario: Edit and save profile
- **WHEN** an admin edits the "email-triage" profile to change model to "claude-sonnet-4-5-20250929" and saves
- **THEN** the profile is updated and the list reflects the change

### Requirement: Delete profile with confirmation
Clicking Delete on a profile SHALL show a confirmation dialog. If confirmed, `DELETE /api/task-profiles/{id}` SHALL be called. The dialog SHALL warn that tasks using this profile will revert to the default.

#### Scenario: Delete confirmed
- **WHEN** an admin clicks Delete on "email-triage" and confirms
- **THEN** the profile is deleted and removed from the list

#### Scenario: Delete cancelled
- **WHEN** an admin clicks Delete and cancels the confirmation
- **THEN** the profile is not deleted

### Requirement: Profile summary display
Each profile card SHALL display a summary showing which fields override the default. Fields set to null (inherit) SHALL show "(default)". Fields set to an empty array SHALL show "None". Fields set to explicit values SHALL show the value or count.

#### Scenario: Profile with mixed overrides
- **WHEN** a profile has `model: "claude-haiku-4-5"`, `mcp_servers: ["gmail"]`, `skills: null`
- **THEN** the card shows "Model: claude-haiku-4-5 · MCP: gmail · Skills: (default)"
