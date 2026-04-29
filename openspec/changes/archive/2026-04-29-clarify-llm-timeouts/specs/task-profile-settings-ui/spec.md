## MODIFIED Requirements

### Requirement: Add Profile button and form
The page SHALL have an "Add Profile" button that opens a form (modal or inline) for creating a new task profile. The form SHALL include fields for: name (text input), description (text input), match rules (textarea), model (dropdown or blank to inherit), system prompt (textarea or blank to inherit), max turns (number input or blank to inherit), reasoning effort (dropdown: low/medium/high or blank to inherit), LLM timeout (number input in seconds, or blank to inherit), MCP servers (selection), LiteLLM MCP servers (selection), and skills (selection). The LLM timeout input SHALL accept positive integers only (`min=1`, integer step). A blank value SHALL be sent to the API as `null` to indicate inheritance from the global `task_processing_timeout` setting.

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

## ADDED Requirements

### Requirement: Profile summary displays LLM timeout
Each profile card's summary SHALL display the `llm_timeout` value when set, using the same convention as other scalar fields: `"(default)"` when the value is null, otherwise the value followed by `"s"`.

#### Scenario: Profile with explicit timeout shown in summary
- **WHEN** a profile has `llm_timeout: 180`
- **THEN** the card summary includes "Timeout: 180s"

#### Scenario: Profile inheriting timeout shown as default
- **WHEN** a profile has `llm_timeout: null`
- **THEN** the card summary includes "Timeout: (default)"
