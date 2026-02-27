## Purpose

Local HTTP bridge API for the macOS app to manage task-runner containers on behalf of the worker.

## Requirements

### Requirement: Local HTTP bridge API for container management
The Swift app SHALL expose a local HTTP API for the worker container to request task-runner container creation. The API SHALL bind to localhost only (or a Unix domain socket) and SHALL require a shared secret token generated at app startup. The token SHALL be passed to the worker container as an environment variable.

#### Scenario: Worker creates a task-runner container
- **WHEN** the worker sends `POST /containers` with image, env vars, and input files
- **THEN** the Swift app creates an Apple Container, injects the files, starts it, and returns the container ID

#### Scenario: Worker streams task-runner logs
- **WHEN** the worker sends `GET /containers/{id}/logs`
- **THEN** the Swift app streams the container's stdout/stderr as Server-Sent Events

#### Scenario: Worker reads task-runner output
- **WHEN** the worker sends `GET /containers/{id}/output` after the container exits
- **THEN** the Swift app returns the contents of `/output/result.json` from the container

#### Scenario: Worker checks task-runner status
- **WHEN** the worker sends `GET /containers/{id}/status`
- **THEN** the Swift app returns the container's status (running/exited) and exit code

#### Scenario: Worker removes task-runner container
- **WHEN** the worker sends `DELETE /containers/{id}`
- **THEN** the Swift app stops (if running) and removes the container

#### Scenario: Unauthorized request rejected
- **WHEN** a request arrives without the correct bearer token
- **THEN** the API returns 401 Unauthorized

### Requirement: Bridge API URL passed to worker
The app SHALL pass the bridge API URL and authentication token to the worker container as environment variables: `CONTAINER_BRIDGE_URL` and `CONTAINER_BRIDGE_TOKEN`. The worker SHALL set `CONTAINER_RUNTIME=apple` to activate the `AppleContainerRuntime`.

#### Scenario: Worker receives bridge configuration
- **WHEN** the worker container starts
- **THEN** it has `CONTAINER_RUNTIME=apple`, `CONTAINER_BRIDGE_URL=http://host.containers.internal:<port>`, and `CONTAINER_BRIDGE_TOKEN=<token>`
