## ADDED Requirements

### Requirement: Claude OAuth token setting
The settings registry SHALL include a `claude_code_oauth_token` key marked sensitive with a default of `""`. The Security settings section SHALL include a "Claude Code Token" card with a password-style input, helper text instructing the user to run `claude setup-token` to generate the value, and Save and Clear actions. Because this is a server-admin credential, the card SHALL live in the local Security section alongside the MCP API key card rather than in `@errand-ai/ui-components`.

#### Scenario: Token saved
- **WHEN** a server admin enters a token and clicks Save
- **THEN** the value is persisted under the `claude_code_oauth_token` setting

#### Scenario: Token returned masked
- **WHEN** the settings API returns `claude_code_oauth_token` to the client
- **THEN** the value is masked by the registry's sensitive-value masking and the plaintext is never sent

#### Scenario: Token cleared
- **WHEN** a server admin clicks Clear
- **THEN** the setting is emptied and subsequent claude containers receive no token

#### Scenario: Non-admin cannot read the token
- **WHEN** a user without server-admin rights requests the settings
- **THEN** the token setting is not exposed in plaintext

### Requirement: Claude token injected into claude images only
When the TaskManager prepares a container whose resolved image is the claude-task-runner image and `claude_code_oauth_token` is non-empty, it SHALL inject the value as the `CLAUDE_CODE_OAUTH_TOKEN` environment variable. When the setting is empty, the variable SHALL NOT be set, which causes the runner to use the standard agent loop. The variable SHALL NOT be injected for any other image, including custom images.

#### Scenario: Token injected for the claude image
- **WHEN** the resolved image is the claude-task-runner image and a token is stored
- **THEN** the container environment includes `CLAUDE_CODE_OAUTH_TOKEN`

#### Scenario: Token absent
- **WHEN** the resolved image is the claude-task-runner image and no token is stored
- **THEN** the container environment does not include `CLAUDE_CODE_OAUTH_TOKEN`

#### Scenario: Default image never receives the token
- **WHEN** the resolved image is the default task-runner image and a token is stored
- **THEN** the container environment does not include `CLAUDE_CODE_OAUTH_TOKEN`

#### Scenario: Custom image never receives the token
- **WHEN** the resolved image is an arbitrary custom image and a token is stored
- **THEN** the container environment does not include `CLAUDE_CODE_OAUTH_TOKEN`

### Requirement: User-facing disclaimer
When the Claude Code Token field holds a value, the Settings UI SHALL display a warning explaining that: (1) tasks will run against the user's personal Claude subscription; (2) usage counts against that subscription's quota; (3) concurrent tasks share the same quota; (4) Anthropic's Terms of Service apply and the feature is intended for personal or local use; and (5) delegated tasks lose the runner's compaction, stall guard, tool-call recovery, and mid-task Google token refresh.

#### Scenario: Disclaimer shown when a token is present
- **WHEN** the Claude Code Token field holds a value
- **THEN** the warning is displayed including the reduced-safety-net point

#### Scenario: No disclaimer when empty
- **WHEN** the Claude Code Token field is empty
- **THEN** no warning is displayed

### Requirement: Token age is recorded, not parsed
The UI SHALL record and display the date the token was saved, together with a note that `claude setup-token` values are documented as valid for approximately one year. The UI SHALL NOT attempt to derive an expiry date from the token itself: `sk-ant-oat01-…` values are opaque strings, not decodable tokens. When the recorded save date is more than eleven months old, the UI SHALL show a renewal reminder.

#### Scenario: Save date displayed
- **WHEN** a token was saved on 2026-07-01
- **THEN** the card shows that save date and the approximate one-year validity note

#### Scenario: Renewal reminder
- **WHEN** the recorded save date is more than eleven months in the past
- **THEN** the card shows a reminder to run `claude setup-token` again

#### Scenario: No expiry claim without a save date
- **WHEN** a token is present but no save date was recorded
- **THEN** the card shows no expiry or renewal claim
