## ADDED Requirements

### Requirement: DinD sidecar in worker deployment
The Helm chart worker Deployment SHALL include a `docker:dind` sidecar container alongside the worker container. The DinD container SHALL run with `privileged: true` in the security context. The DinD container SHALL have `DOCKER_TLS_CERTDIR` set to an empty string to disable TLS. The worker container SHALL have `DOCKER_HOST` set to `tcp://localhost:2375` to communicate with the DinD sidecar via the pod's shared network namespace.

#### Scenario: Worker pod includes DinD sidecar
- **WHEN** the Helm chart is deployed
- **THEN** the worker pod contains two containers: `worker` and `dind`

#### Scenario: DinD runs privileged
- **WHEN** the worker pod starts
- **THEN** the `dind` container has `privileged: true` in its security context

#### Scenario: Worker connects to DinD
- **WHEN** the worker container starts
- **THEN** the `DOCKER_HOST` environment variable is set to `tcp://localhost:2375`

### Requirement: Task runner image configurable in values
The Helm chart values SHALL include a `taskRunner.image.repository` and `taskRunner.image.tag` configuration. The `tag` SHALL default to the chart's `appVersion` (same as frontend and backend images). The worker container SHALL have a `TASK_RUNNER_IMAGE` environment variable set to the fully-qualified task runner image reference.

#### Scenario: Default task runner image tag
- **WHEN** `taskRunner.image.tag` is empty in values
- **THEN** the worker container's `TASK_RUNNER_IMAGE` env var uses the chart's `appVersion` as the tag

#### Scenario: Custom task runner image tag
- **WHEN** `taskRunner.image.tag` is set to `1.0.0` in values
- **THEN** the worker container's `TASK_RUNNER_IMAGE` env var uses `1.0.0` as the tag

### Requirement: DinD image configurable in values
The Helm chart values SHALL include a `dind.image` configuration (default `docker:27-dind`) for the DinD sidecar image.

#### Scenario: Default DinD image
- **WHEN** `dind.image` is not set in values
- **THEN** the DinD sidecar uses `docker:27-dind`

#### Scenario: Custom DinD image
- **WHEN** `dind.image` is set to `docker:26-dind` in values
- **THEN** the DinD sidecar uses `docker:26-dind`
