## ADDED Requirements

### Requirement: Container image resolution from profile
When the TaskManager prepares a container for a task whose resolved profile has a `container_image` value, it SHALL resolve the image as follows: `null` uses the `TASK_RUNNER_IMAGE` environment variable; the literal `"claude"` uses the `CLAUDE_TASK_RUNNER_IMAGE` environment variable (default `claude-task-runner:latest`); any other string is used verbatim as an image reference. A task with no profile SHALL continue to use `TASK_RUNNER_IMAGE`.

#### Scenario: Default image (null)
- **WHEN** the profile has `container_image: null`
- **THEN** the container uses the value of `TASK_RUNNER_IMAGE`

#### Scenario: Claude image
- **WHEN** the profile has `container_image: "claude"`
- **THEN** the container uses the value of `CLAUDE_TASK_RUNNER_IMAGE`, defaulting to `claude-task-runner:latest`

#### Scenario: Custom image
- **WHEN** the profile has `container_image: "my-registry/custom-runner:v2"`
- **THEN** the container uses `my-registry/custom-runner:v2`

#### Scenario: Task without profile
- **WHEN** a task has `profile_id = null`
- **THEN** the container uses `TASK_RUNNER_IMAGE`, unchanged from current behaviour

### Requirement: Image selection is an administrative action
A custom `container_image` receives the same injected material as the default image, including the SSH private key, GitHub token, MCP bearer token, and per-task environment variables. The API SHALL therefore restrict setting `container_image` to users who are already permitted to create or edit task profiles, and SHALL NOT accept the field from any unauthenticated or task-scoped caller.

#### Scenario: Profile editor may set the image
- **WHEN** a user permitted to edit task profiles submits a profile with `container_image: "claude"`
- **THEN** the value is accepted and persisted

#### Scenario: Unauthorised caller rejected
- **WHEN** a caller without profile-edit rights attempts to set `container_image`
- **THEN** the request is rejected and no image change is persisted

### Requirement: Profile knobs without meaning on the claude image
`MAX_TURNS`, `LLM_REQUEST_TIMEOUT`, and the profile's resolved LLM provider have no effect when the task is delegated to the CLI; only reasoning effort and a Claude model name map onto CLI flags. The TaskManager SHALL still inject the standard environment so the fallback path works, and the resolution behaviour SHALL be documented so operators do not read those fields as active.

#### Scenario: Standard environment still injected
- **WHEN** a container is prepared for the claude image
- **THEN** the standard task-runner environment variables are injected so a fallback run behaves normally

#### Scenario: Provider credentials still resolved
- **WHEN** the profile names an LLM provider and the claude image is selected
- **THEN** the provider's base URL and key are injected for the fallback path, and delegation ignores them
