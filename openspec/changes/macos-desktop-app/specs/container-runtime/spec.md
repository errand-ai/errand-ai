## ADDED Requirements

### Requirement: AppleContainerRuntime implementation
The worker SHALL include an `AppleContainerRuntime` implementation of the `ContainerRuntime` interface. This runtime SHALL communicate with the macOS app's bridge API to create, monitor, and clean up task-runner containers. The runtime SHALL be selected when `CONTAINER_RUNTIME` is set to `apple`.

#### Scenario: Apple runtime creates container via bridge API
- **WHEN** `AppleContainerRuntime.prepare()` is called with an image, env vars, and files
- **THEN** the runtime sends `POST /containers` to the bridge API with the container specification

#### Scenario: Apple runtime streams logs via bridge API
- **WHEN** `AppleContainerRuntime.run()` is called
- **THEN** the runtime opens an SSE connection to `GET /containers/{id}/logs` and yields log lines

#### Scenario: Apple runtime reads output via bridge API
- **WHEN** `AppleContainerRuntime.result()` is called after the container exits
- **THEN** the runtime reads the exit code from `GET /containers/{id}/status` and the structured output from `GET /containers/{id}/output`

#### Scenario: Apple runtime cleans up via bridge API
- **WHEN** `AppleContainerRuntime.cleanup()` is called
- **THEN** the runtime sends `DELETE /containers/{id}` to remove the container
