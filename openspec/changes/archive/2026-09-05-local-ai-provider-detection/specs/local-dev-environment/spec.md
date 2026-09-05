## ADDED Requirements

### Requirement: Compose declares a host gateway for services that reach host AI runtimes

The compose environments SHALL map a host gateway name to the container host for the errand service and for the memory service, so that a locally running AI runtime on the host is reachable from inside those containers. The mapping SHALL use the container engine's host-gateway facility rather than a hard-coded address, so that it works on both Docker Desktop and Linux.

#### Scenario: errand service can reach the host

- **WHEN** the compose environment is brought up and an OpenAI-compatible service is listening on the host
- **THEN** the errand container can reach it via the host gateway name

#### Scenario: memory service can reach the host

- **WHEN** the memory service is configured to use a host-run LLM endpoint
- **THEN** the memory container resolves the host gateway name to the container host

#### Scenario: Named task-runner network retained

- **WHEN** the compose environment is brought up
- **THEN** a named task-runner network is configured, so that locally detected providers are usable
