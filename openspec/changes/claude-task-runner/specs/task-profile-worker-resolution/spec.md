## ADDED Requirements

### Requirement: Container image resolution from profile
When the TaskManager prepares a container for a task with a non-null `profile_id`, it SHALL resolve the container image from the profile's `container_image` field. If `container_image` is null, the default `TASK_RUNNER_IMAGE` environment variable SHALL be used. If `container_image` is `"claude"`, the `CLAUDE_TASK_RUNNER_IMAGE` environment variable SHALL be used (defaulting to `claude-task-runner:latest`). Any other string SHALL be used as-is as the container image reference.

#### Scenario: Default image (null)
- **WHEN** the profile has `container_image: null`
- **THEN** the container uses the value of `TASK_RUNNER_IMAGE` env var

#### Scenario: Claude image
- **WHEN** the profile has `container_image: "claude"`
- **THEN** the container uses the value of `CLAUDE_TASK_RUNNER_IMAGE` env var (default: `claude-task-runner:latest`)

#### Scenario: Custom image
- **WHEN** the profile has `container_image: "my-registry/custom-runner:v2"`
- **THEN** the container uses `my-registry/custom-runner:v2` as the image

#### Scenario: Task without profile
- **WHEN** a task has `profile_id = null`
- **THEN** the container uses the default `TASK_RUNNER_IMAGE` env var (no change in behavior)
