## ADDED Requirements

### Requirement: Optional workspace gateway in docker-compose

The compose stack SHALL support an optional workspace gateway service (same rclone image and configuration shape as the Kubernetes gateway, including the token-refresher behavior) attached to the errand network. Task containers with workspace-enabled profiles SHALL reach it via an NFS volume (`driver_opts: type=nfs`) or a bind-mount fallback for local testing. The service SHALL be disabled by default (compose profile or commented block) so `docker compose up` behavior is unchanged for existing users.

#### Scenario: Default compose unchanged

- **WHEN** the stack is started without the workspace profile
- **THEN** no gateway container runs and existing services behave as before

#### Scenario: Gateway service started

- **WHEN** the stack is started with the workspace profile enabled and provider credentials configured
- **THEN** the gateway serves the configured cloud folder and a workspace-enabled task container can read and write files through its mount
