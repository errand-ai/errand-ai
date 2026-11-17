## ADDED Requirements

### Requirement: Task-scoped credentials and enforceable isolation
External attempts SHALL run within a qualified container/VM boundary with isolated HOME/config/session/workspace, least privilege, bounded resources and enforced filesystem/network policy. The system SHALL NOT rely on prompts, working directory, hooks or native approvals as the sole sandbox. Credential references SHALL be authorized by principal/profile and resolved only for the selected adapter. Secrets SHALL NOT enter argv, prompts, events, exports, images or retained debug artifacts. Teardown SHALL revoke scoped access and remove ephemeral secrets.

#### Scenario: Cross-profile secret and filesystem access
- **WHEN** a harness or project-supplied extension attempts access to another profile's home, secrets, session or unmounted host path
- **THEN** the external boundary denies access and records a redacted policy failure

#### Scenario: Native sandbox cannot initialize
- **WHEN** a pinned vendor sandbox fails on a runtime
- **THEN** launch fails unless an explicitly qualified outer-sandbox contract already covers that tuple and no automatic dangerous bypass is applied

#### Scenario: Claude consumer credentials supplied to settings
- **WHEN** a user attempts to store a Claude.ai subscription/session token for third-party-mediated execution
- **THEN** this rollout rejects that mode and offers only the approved credential route without claiming zero incremental cost

### Requirement: Scoped MCP broker and one owner per tool
The system SHALL authorize task-scoped MCP tools at the broker, excluding administration/evaluation/secret/profile-mutation capabilities unless separately authorized. It SHALL verify required servers and allowed catalogs before model execution. Each native/service capability SHALL have an explicit owner to prevent duplicate execution. Unreviewed global/project MCP, executable hooks and recursive delegation SHALL NOT be loaded implicitly.

#### Scenario: Client ignores an excluded tool
- **WHEN** an external harness directly requests a denied MCP method
- **THEN** broker authorization denies it independent of client tool filtering

#### Scenario: Required MCP server disappears silently
- **WHEN** a configured required server fails handshake or yields no expected authorized catalog
- **THEN** preparation fails without running the model or falling back

#### Scenario: Duplicate shell and messaging tools
- **WHEN** an external native catalog overlaps forwarded tools
- **THEN** the approved ownership policy keeps native filesystem/shell execution within isolation and service mutations with the scoped broker without duplicate aliases executing the same action

### Requirement: Unattended approval policy
Initial external adapters SHALL support deny-by-default unattended permissions. An operation requiring an unavailable human approval SHALL terminate with `approval_required` or `permission_denied`, not wait indefinitely or grant itself permission. Future interactive approval support SHALL require separately qualified correlated, RBAC-controlled, time-bounded response handling.

#### Scenario: Harness requests wider permissions without a human channel
- **WHEN** a scheduled attempt requests an unapproved operation
- **THEN** it is denied and ends or continues only within its approved policy, without blanket bypass
