## ADDED Requirements

### Requirement: Claude OAuth token credential storage
The Settings UI SHALL include a field for storing a Claude Code OAuth token under the Credentials section. The field SHALL be labelled "Claude Code Token" with helper text explaining that users should run `claude setup-token` to generate the value. The token SHALL be stored as a credential with key `CLAUDE_CODE_OAUTH_TOKEN`.

#### Scenario: User saves Claude token
- **WHEN** a user enters a token starting with `sk-ant-oat01-` in the Claude Code Token field and saves
- **THEN** the credential is stored with key `CLAUDE_CODE_OAUTH_TOKEN` and the value is encrypted in the database

#### Scenario: Token field shows masked value
- **WHEN** a user views the Credentials settings with a stored Claude token
- **THEN** the field shows a masked value (e.g., `sk-ant-oat01-...xxxx`)

### Requirement: Claude token injected into claude-task-runner containers
When the TaskManager prepares a container using the claude-task-runner image and a `CLAUDE_CODE_OAUTH_TOKEN` credential exists, the token SHALL be injected as the `CLAUDE_CODE_OAUTH_TOKEN` environment variable. If no token is stored, the environment variable SHALL NOT be set (allowing the task-runner fallback to standard agent loop).

#### Scenario: Token injected when present
- **WHEN** TaskManager prepares a claude-task-runner container and `CLAUDE_CODE_OAUTH_TOKEN` credential exists
- **THEN** the container environment includes `CLAUDE_CODE_OAUTH_TOKEN=<token value>`

#### Scenario: Token not injected when absent
- **WHEN** TaskManager prepares a claude-task-runner container and no `CLAUDE_CODE_OAUTH_TOKEN` credential exists
- **THEN** the container environment does not include `CLAUDE_CODE_OAUTH_TOKEN`

#### Scenario: Token not injected for default image
- **WHEN** TaskManager prepares a default task-runner container (not claude image)
- **THEN** the container environment does not include `CLAUDE_CODE_OAUTH_TOKEN` regardless of credential existence

### Requirement: User-facing disclaimer
When a user saves a `CLAUDE_CODE_OAUTH_TOKEN` credential, the Settings UI SHALL display a warning banner explaining: (1) this uses their personal Claude Max subscription, (2) usage counts against their subscription quota, (3) concurrent tasks share the same quota, (4) Anthropic's Terms of Service apply, and (5) this feature is for personal/local use only.

#### Scenario: Disclaimer shown on token entry
- **WHEN** a user enters a value in the Claude Code Token field
- **THEN** a warning banner is displayed with the ToS and usage disclaimers

#### Scenario: Disclaimer not shown when field is empty
- **WHEN** the Claude Code Token field is empty
- **THEN** no warning banner is displayed

### Requirement: Token expiry display
The Settings UI SHALL display the token's expiry date if it can be determined. The `claude setup-token` tokens are valid for 1 year. If the token is within 30 days of expiry, the UI SHALL show a warning indicating the token needs renewal.

#### Scenario: Token expiry shown
- **WHEN** a valid Claude token is stored and its expiry can be parsed
- **THEN** the UI shows "Expires: <date>" below the token field

#### Scenario: Expiry warning
- **WHEN** the token expires within 30 days
- **THEN** the UI shows an amber warning "Token expires in X days — run `claude setup-token` to renew"
