## MODIFIED Requirements

### Requirement: Settings page layout
The Settings page SHALL use a sidebar navigation layout with five sub-pages. The existing four remain: "Agent Configuration" (`/settings/agent`), "Task Management" (`/settings/tasks`), "Security" (`/settings/security`), and "Integrations" (`/settings/integrations`). A new fifth sub-page "User Management" (`/settings/users`) SHALL be added.

#### Scenario: Settings sidebar shows five items
- **WHEN** an admin navigates to any settings sub-page
- **THEN** the sidebar displays five links including "User Management"

### Requirement: Settings fields display source metadata
All settings input fields SHALL adapt based on the `source` and `readonly` metadata returned by `GET /api/settings`. When a setting has `readonly: true`, the input field SHALL be disabled with a lock icon and a tooltip or label indicating "Set via environment variable". When a setting has `sensitive: true` and `source: "env"`, the displayed value SHALL be the masked value from the API.

#### Scenario: Env-sourced setting shown read-only
- **WHEN** the settings page loads and `openai_base_url` has `source: "env"` and `readonly: true`
- **THEN** the field is disabled with a lock indicator

#### Scenario: DB-sourced setting is editable
- **WHEN** the settings page loads and `system_prompt` has `source: "database"` and `readonly: false`
- **THEN** the field is editable as before

#### Scenario: Sensitive env-sourced value is masked
- **WHEN** the settings page loads and `openai_api_key` has `sensitive: true` and `source: "env"`
- **THEN** the field shows the masked value (e.g., `sk-p****`) and is disabled
