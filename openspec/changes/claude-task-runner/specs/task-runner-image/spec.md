## ADDED Requirements

### Requirement: Custom task-runner image documentation
The repository SHALL include documentation (in `task-runner/CUSTOM_IMAGES.md` or equivalent) explaining how users can create custom task-runner images by extending the base image. The documentation SHALL include a sample Dockerfile using `FROM errand-task-runner:latest` as the base, instructions for adding custom tools or dependencies, and guidelines for maintaining compatibility with the task-runner entrypoint and event protocol.

#### Scenario: Documentation exists
- **WHEN** a user wants to create a custom task-runner image
- **THEN** they can find documentation in the task-runner directory explaining the base image extension pattern

#### Scenario: Sample Dockerfile provided
- **WHEN** a user reads the custom image documentation
- **THEN** they find a working example Dockerfile that extends the base task-runner image
