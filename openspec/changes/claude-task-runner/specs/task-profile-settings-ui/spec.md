## MODIFIED Requirements

### Requirement: Add Profile button and form
The page SHALL have an "Add Profile" button that opens a form (modal or inline) for creating a new task profile. The form SHALL include fields for: name (text input), description (text input), match rules (textarea), model (dropdown or blank to inherit), system prompt (textarea or blank to inherit), max turns (number input or blank to inherit), reasoning effort (dropdown: low/medium/high or blank to inherit), LLM timeout (number input in seconds, or blank to inherit), **container image (radio: Default / Claude / Custom, with a text input shown when Custom is selected)**, MCP servers (selection), LiteLLM MCP servers (selection), and skills (selection). The LLM timeout input SHALL accept positive integers only (`min=1`, integer step). A blank value SHALL be sent to the API as `null` to indicate inheritance from the global `task_processing_timeout` setting.

The "Claude" option SHALL be offered only when the backend reports `claude_supported: true`. When "Claude" is the selected image, the max turns, LLM timeout, and model fields SHALL be disabled with an explanatory note, because they have no effect on a delegated run.

The form is rendered by `<TaskProfileListCard>` from `@errand-ai/ui-components`; this requirement is satisfied by a released version of that package plus a dependency bump in this repository.

#### Scenario: Create a profile
- **WHEN** an admin fills in the form with name "email-triage", model "claude-haiku-4-5-20251001", and clicks Save
- **THEN** `POST /api/task-profiles` is called and the new profile appears in the list

#### Scenario: Validation error on duplicate name
- **WHEN** an admin tries to create a profile with a name that already exists
- **THEN** an error toast is shown with the conflict message

#### Scenario: Create profile with explicit LLM timeout override
- **WHEN** an admin enters `300` in the LLM timeout field and saves
- **THEN** the profile is saved with `llm_timeout: 300`

#### Scenario: Create profile inheriting LLM timeout
- **WHEN** an admin leaves the LLM timeout field blank and saves
- **THEN** the profile is saved with `llm_timeout: null`

#### Scenario: Editing a profile loads existing LLM timeout
- **WHEN** an admin edits a profile with `llm_timeout: 120`
- **THEN** the form's LLM timeout input is pre-populated with `120`

#### Scenario: Editing a profile loads inherit state
- **WHEN** an admin edits a profile with `llm_timeout: null`
- **THEN** the form's LLM timeout input is blank

#### Scenario: Create profile with claude image
- **WHEN** an admin selects "Claude" for container image and saves
- **THEN** the profile is saved with `container_image: "claude"`

#### Scenario: Create profile with custom image
- **WHEN** an admin selects "Custom" for container image and enters "my-registry/custom-runner:v1"
- **THEN** the profile is saved with `container_image: "my-registry/custom-runner:v1"`

#### Scenario: Create profile with default image
- **WHEN** an admin selects "Default" for container image, or leaves the group unchanged
- **THEN** the profile is saved with `container_image: null`

#### Scenario: Claude option hidden when unsupported
- **WHEN** the backend reports `claude_supported: false` and an admin opens the profile form
- **THEN** the container image radio group does not offer the "Claude" option

#### Scenario: Inapplicable fields disabled for the claude image
- **WHEN** an admin selects "Claude" for container image
- **THEN** the max turns, LLM timeout, and model fields are disabled with a note that they do not apply to delegated runs

### Requirement: Profile summary display
Each profile card SHALL display a summary showing which fields override the default. Fields set to null (inherit) SHALL show "(default)". Fields set to an empty array SHALL show "None". Fields set to explicit values SHALL show the value or count. **The container image SHALL be shown as "Image: Claude" for the claude image, "Image: `<reference>`" for a custom image, and "Image: (default)" when null.**

#### Scenario: Profile with mixed overrides
- **WHEN** a profile has `model: "claude-haiku-4-5"`, `mcp_servers: ["gmail"]`, `skills: null`
- **THEN** the card shows "Model: claude-haiku-4-5 · MCP: gmail · Skills: (default)"

#### Scenario: Profile with claude image
- **WHEN** a profile has `container_image: "claude"`
- **THEN** the card summary includes "Image: Claude"

#### Scenario: Profile with custom image
- **WHEN** a profile has `container_image: "my-registry/custom-runner:v1"`
- **THEN** the card summary includes "Image: my-registry/custom-runner:v1"

#### Scenario: Profile with default image
- **WHEN** a profile has `container_image: null`
- **THEN** the card summary includes "Image: (default)"
