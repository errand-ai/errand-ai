## MODIFIED Requirements

### Requirement: Test connection inline feedback

All "Test Connection" actions in the application SHALL provide inline visual feedback for both success and failure states, displayed near the button. The feedback SHALL use green text for success and red text for failure, matching the existing error message styling pattern.

Success feedback SHALL persist until the user modifies the relevant input fields (e.g., URL, API key), at which point it SHALL be cleared. The "Test Connection" button text SHALL change to "Connection Verified" with a checkmark indicator after a successful test, reverting when inputs change.

Toast notifications SHALL be retained as secondary feedback in addition to the inline indicators.

#### Scenario: Setup wizard LLM test connection success
- **WHEN** the user clicks "Test Connection" on the setup wizard's LLM Provider step and the connection succeeds
- **THEN** a green inline success message "Connection successful" is displayed near the button, the button text changes to "Connection Verified", and a toast notification appears

#### Scenario: Setup wizard LLM test connection failure
- **WHEN** the user clicks "Test Connection" on the setup wizard's LLM Provider step and the connection fails
- **THEN** a red inline error message is displayed near the button (existing behavior, unchanged)

#### Scenario: Setup wizard success cleared on input change
- **WHEN** the user has a successful test result and then modifies the provider URL or API key
- **THEN** the inline success message and "Connection Verified" button state are cleared

#### Scenario: OIDC test connection success on User Management page
- **WHEN** the admin clicks "Test Connection" on the OIDC configuration section and the discovery URL is valid
- **THEN** a green inline success message "OIDC discovery URL is valid" is displayed near the button and a toast notification appears

#### Scenario: OIDC test connection failure
- **WHEN** the admin clicks "Test Connection" on the OIDC configuration section and the connection fails
- **THEN** a red inline error message is displayed near the button (existing behavior, unchanged)
