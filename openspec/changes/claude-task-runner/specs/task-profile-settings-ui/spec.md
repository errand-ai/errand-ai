## MODIFIED Requirements

### Requirement: Add Profile button and form
The page SHALL have an "Add Profile" button that opens a form (modal or inline) for creating a new task profile. The form SHALL include fields for: name (text input), description (text input), match rules (textarea), model (dropdown or blank to inherit), system prompt (textarea or blank to inherit), max turns (number input or blank to inherit), reasoning effort (dropdown: low/medium/high or blank to inherit), **container image (radio: Default / Claude / Custom)**, MCP servers (selection), LiteLLM MCP servers (selection), and skills (selection).

#### Scenario: Create a profile
- **WHEN** an admin fills in the form with name "email-triage", model "claude-haiku-4-5-20251001", and clicks Save
- **THEN** `POST /api/task-profiles` is called and the new profile appears in the list

#### Scenario: Validation error on duplicate name
- **WHEN** an admin tries to create a profile with a name that already exists
- **THEN** an error toast is shown with the conflict message

#### Scenario: Create profile with claude image
- **WHEN** an admin selects "Claude" for container image and saves
- **THEN** the profile is saved with `container_image: "claude"`

#### Scenario: Create profile with custom image
- **WHEN** an admin selects "Custom" for container image and enters "my-registry/custom-runner:v1"
- **THEN** the profile is saved with `container_image: "my-registry/custom-runner:v1"`

#### Scenario: Create profile with default image
- **WHEN** an admin selects "Default" for container image (or leaves unchanged)
- **THEN** the profile is saved with `container_image: null`

#### Scenario: Claude option hidden on K8s deployments
- **WHEN** the errand server has `CONTAINER_RUNTIME=kubernetes` and the admin opens the profile form
- **THEN** the container image radio group does not include the "Claude" option

### Requirement: Profile summary display
Each profile card SHALL display a summary showing which fields override the default. Fields set to null (inherit) SHALL show "(default)". Fields set to an empty array SHALL show "None". Fields set to explicit values SHALL show the value or count. **The container image field SHALL show "Default", "Claude", or the custom image name.**

#### Scenario: Profile with mixed overrides
- **WHEN** a profile has `model: "claude-haiku-4-5"`, `mcp_servers: ["gmail"]`, `skills: null`, `container_image: "claude"`
- **THEN** the card shows "Model: claude-haiku-4-5 · Image: Claude · MCP: gmail · Skills: (default)"

#### Scenario: Profile with default image
- **WHEN** a profile has `container_image: null`
- **THEN** the card shows "Image: (default)" or omits the image field
