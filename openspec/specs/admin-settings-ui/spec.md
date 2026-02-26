## Requirements

### Requirement: Vue Router with two routes
The frontend SHALL use Vue Router with two routes: `/` rendering the Kanban board and `/settings` rendering the Settings page. The router SHALL be configured in history mode. The `App.vue` template SHALL use `<router-view>` in place of direct component rendering.

#### Scenario: Root route shows kanban board
- **WHEN** an authenticated user navigates to `/`
- **THEN** the Kanban board is rendered

#### Scenario: Settings route shows settings page
- **WHEN** an authenticated admin user navigates to `/settings`
- **THEN** the Settings page is rendered

### Requirement: Settings route requires admin role
The `/settings` route SHALL have a navigation guard that checks `isAdmin` from the auth store. If the user is not an admin, the guard SHALL redirect to `/`.

#### Scenario: Admin navigates to settings
- **WHEN** an admin user navigates to `/settings`
- **THEN** the Settings page is rendered

#### Scenario: Non-admin navigates to settings
- **WHEN** a non-admin user navigates to `/settings`
- **THEN** the user is redirected to `/`

#### Scenario: Unauthenticated user navigates to settings
- **WHEN** an unauthenticated user navigates to `/settings`
- **THEN** the user is redirected to `/auth/login` (handled by existing auth logic)

### Requirement: Settings page layout
The Settings page SHALL use a sidebar navigation layout with five sub-pages. The **"Agent Configuration"** sub-page (`/settings/agent`) SHALL contain "System Prompt", "Skills", "Skills Repository", and "MCP Server Configuration" sections (in that order). The **"Task Management"** sub-page (`/settings/tasks`) SHALL contain "LLM Models" and "Task Management" sections (in that order). The **"Security"** sub-page (`/settings/security`) SHALL contain "Git SSH Key" and "MCP API Key" sections. The **"Integrations"** sub-page (`/settings/integrations`) SHALL contain the platform integrations section followed by the LiteLLM MCP Servers section (conditionally visible). The **"User Management"** sub-page (`/settings/users`) SHALL contain authentication mode and local admin account sections. The "MCP Server Configuration" section SHALL remain collapsible.

Each settings section SHALL remain a separate Vue component in `frontend/src/components/settings/`:
- `SystemPromptSettings.vue`
- `SkillsSettings.vue`
- `SkillsRepoSettings.vue`
- `LlmModelSettings.vue`
- `TaskManagementSettings.vue` (consolidated: timezone, archiving, runner log level)
- `McpApiKeySettings.vue`
- `GitSshKeySettings.vue`
- `McpServerConfigSettings.vue`
- `LitellmMcpSettings.vue`

Four sub-page components SHALL exist in `frontend/src/pages/settings/`:
- `AgentConfigurationPage.vue`
- `TaskManagementPage.vue`
- `SecurityPage.vue`
- `IntegrationsPage.vue`

#### Scenario: Settings sidebar shows five items
- **WHEN** an admin navigates to any settings sub-page
- **THEN** the sidebar displays five links including "User Management"

#### Scenario: Agent Configuration sub-page renders its sections
- **WHEN** an admin navigates to `/settings/agent`
- **THEN** the page displays System Prompt, Skills, Skills Repository, and MCP Server Configuration sections

#### Scenario: Task Management sub-page renders its sections
- **WHEN** an admin navigates to `/settings/tasks`
- **THEN** the page displays LLM Models and Task Management sections

#### Scenario: Security sub-page renders its sections
- **WHEN** an admin navigates to `/settings/security`
- **THEN** the page displays Git SSH Key and MCP API Key sections

#### Scenario: Integrations sub-page renders platform and LiteLLM sections
- **WHEN** an admin navigates to `/settings/integrations` and LiteLLM is detected
- **THEN** the page displays platform integrations followed by the LiteLLM MCP Servers section

#### Scenario: Integrations sub-page renders only platforms when no LiteLLM
- **WHEN** an admin navigates to `/settings/integrations` and LiteLLM is not detected
- **THEN** the page displays only the platform integrations section

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

### Requirement: Consistent explicit save pattern
All settings sections SHALL use explicit Save buttons. The three previously auto-saving controls (LLM model dropdowns, Timezone dropdown, Task Runner Log Level dropdown) SHALL no longer auto-save on change. Instead, they SHALL require the user to click a Save button. Each section SHALL track whether its current values differ from the last-saved values. When a section has unsaved changes, it SHALL display a "Unsaved changes" indicator (`text-xs text-amber-600`) near its Save button.

The active sub-page SHALL register a `beforeunload` event listener when any child section has unsaved changes. The listener SHALL show the browser's native "Leave page?" confirmation when the user attempts to navigate away from the settings pages entirely.

#### Scenario: LLM model requires explicit save
- **WHEN** an admin changes the Default Model dropdown
- **THEN** the change is not saved until the user clicks the Save button and an "Unsaved changes" indicator appears

#### Scenario: Timezone requires explicit save
- **WHEN** an admin changes the timezone dropdown
- **THEN** the change is not saved until the user clicks the Save button

#### Scenario: Unsaved changes indicator
- **WHEN** an admin modifies any setting without saving
- **THEN** a "Unsaved changes" label appears in amber near the Save button

#### Scenario: Beforeunload guard
- **WHEN** any settings section on the active sub-page has unsaved changes and the user attempts to navigate away from settings
- **THEN** the browser shows a "Leave page?" confirmation dialog

#### Scenario: No guard when all saved
- **WHEN** all settings sections on the active sub-page have their saved values unchanged
- **THEN** navigating away does not trigger any confirmation

### Requirement: Skill deletion confirmation
The Skills section SHALL display a confirmation dialog before deleting a skill. When the user clicks the Delete button on a skill, a `<dialog>` confirmation modal SHALL appear asking "Delete this skill?" with the skill name displayed. The dialog SHALL have "Cancel" and "Delete" buttons. Only clicking "Delete" in the confirmation SHALL proceed with the deletion.

#### Scenario: Delete button shows confirmation
- **WHEN** an admin clicks Delete on a skill named "twitter-poster"
- **THEN** a confirmation dialog appears with text "Delete this skill?" and the skill name "twitter-poster"

#### Scenario: Cancel preserves skill
- **WHEN** the delete confirmation dialog is shown and the user clicks Cancel
- **THEN** the dialog closes and the skill is not deleted

#### Scenario: Confirm deletes skill
- **WHEN** the delete confirmation dialog is shown and the user clicks Delete
- **THEN** the skill is deleted and a success toast is shown

### Requirement: Settings skeleton loading state
While settings are loading, the page SHALL display skeleton placeholders that match the expected card layout using `animate-pulse` on gray rounded rectangles. The "Loading settings..." text SHALL be replaced by skeleton placeholders.

#### Scenario: Skeleton shown during settings load
- **WHEN** the Settings page is fetching settings for the first time
- **THEN** skeleton card placeholders are shown instead of "Loading settings..." text

### Requirement: Settings empty state for skills
When no skills exist, the Skills section SHALL display a centered empty state with an icon, "No skills configured" text, and guidance "Add skills to give the agent specialised capabilities." instead of showing an empty list.

#### Scenario: Skills empty state
- **WHEN** the Skills section loads with zero skills configured
- **THEN** it displays a centered empty state with icon and guidance text

### Requirement: System prompt editor
The Settings page SHALL display a textarea for editing the system prompt. The textarea SHALL load the current value from `GET /api/settings` on mount. A "Save" button SHALL send the updated value via `PUT /api/settings` with the key `system_prompt`.

#### Scenario: Load existing system prompt
- **WHEN** the Settings page loads and a `system_prompt` setting exists
- **THEN** the textarea displays the current system prompt value

#### Scenario: No existing system prompt
- **WHEN** the Settings page loads and no `system_prompt` setting exists
- **THEN** the textarea is empty

#### Scenario: Save system prompt
- **WHEN** the admin edits the system prompt text and clicks "Save"
- **THEN** the frontend sends `PUT /api/settings` with `{"system_prompt": "<new value>"}` and displays a success indication

### Requirement: MCP server configuration placeholder
The Settings page SHALL display an editable section for MCP server configuration. The section SHALL include an expandable text box (collapsed by default) where the admin can view and edit the MCP server configuration as JSON text. A "Save" button SHALL send the updated value via `PUT /api/settings` with the key `mcp_servers`. The section SHALL load the current value from `GET /api/settings` on mount.

#### Scenario: MCP section with no existing config
- **WHEN** the Settings page loads and no `mcp_servers` setting exists
- **THEN** the MCP section displays an empty expandable text box with placeholder text

#### Scenario: MCP section with existing config
- **WHEN** the Settings page loads and an `mcp_servers` setting exists
- **THEN** the MCP section displays the configuration as editable formatted JSON in the expandable text box

#### Scenario: Save MCP configuration
- **WHEN** the admin edits the MCP server configuration text and clicks "Save"
- **THEN** the frontend sends `PUT /api/settings` with `{"mcp_servers": <parsed JSON>}` and displays a success indication

#### Scenario: Invalid JSON rejected
- **WHEN** the admin enters invalid JSON in the MCP configuration text box and clicks "Save"
- **THEN** the frontend displays a validation error and does not send the API request

#### Scenario: Expand and collapse
- **WHEN** the admin clicks the MCP server configuration section header
- **THEN** the text box expands to show the full configuration, or collapses if already expanded

### Requirement: Settings page error handling
The Settings page SHALL display an error message if the `GET /api/settings` request fails or if a `PUT /api/settings` request fails. A 403 response SHALL display "Access denied -- admin role required."

#### Scenario: API returns 403
- **WHEN** the settings API returns HTTP 403
- **THEN** the page displays "Access denied -- admin role required."

#### Scenario: API returns network error
- **WHEN** the settings API request fails due to a network error
- **THEN** the page displays a generic error message

### Requirement: LLM model selector on settings page
The Settings page SHALL display a "LLM Model" section with a dropdown to select the active LLM model. The dropdown SHALL be populated by calling `GET /api/llm/models`. The current selection SHALL be loaded from `GET /api/settings` (key `llm_model`). If no `llm_model` setting exists, the dropdown SHALL default to `claude-haiku-4-5-20251001`. Changing the selection SHALL immediately save the choice via `PUT /api/settings` with `{"llm_model": "<selected>"}`. The dropdown SHALL be labelled "Title Generation Model" to distinguish it from the task processing model.

#### Scenario: Model dropdown loads with current selection
- **WHEN** the Settings page loads and the `llm_model` setting is "gpt-4o-mini"
- **THEN** the dropdown shows available models with "gpt-4o-mini" selected

#### Scenario: Model dropdown with default
- **WHEN** the Settings page loads and no `llm_model` setting exists
- **THEN** the dropdown shows available models with "claude-haiku-4-5-20251001" selected

#### Scenario: Change model selection
- **WHEN** the admin selects a different model from the dropdown
- **THEN** the frontend sends `PUT /api/settings` with the new `llm_model` value and shows a success indication

#### Scenario: Models endpoint unavailable
- **WHEN** the Settings page loads and `GET /api/llm/models` fails
- **THEN** the dropdown is disabled and an error message is displayed indicating the model list could not be loaded

### Requirement: Task processing model selector on settings page
The Settings page SHALL display a "Default Model" dropdown (previously labelled "Task Processing Model") within the "LLM Models" section on the Task Management sub-page. The dropdown SHALL be populated by calling `GET /api/llm/models` (same endpoint as the title-generation model). The current selection SHALL be loaded from `GET /api/settings` (key `task_processing_model`). If no `task_processing_model` setting exists, the dropdown SHALL default to `claude-sonnet-4-5-20250929`. Changing the selection SHALL immediately save the choice via `PUT /api/settings` with `{"task_processing_model": "<selected>"}`.

#### Scenario: Task processing model dropdown loads with current selection
- **WHEN** the Settings page loads and the `task_processing_model` setting is "claude-sonnet-4-5-20250929"
- **THEN** the "Default Model" dropdown shows available models with "claude-sonnet-4-5-20250929" selected

#### Scenario: Task processing model dropdown with default
- **WHEN** the Settings page loads and no `task_processing_model` setting exists
- **THEN** the "Default Model" dropdown shows available models with "claude-sonnet-4-5-20250929" selected

#### Scenario: Change task processing model
- **WHEN** the admin selects a different model from the "Default Model" dropdown
- **THEN** the frontend sends `PUT /api/settings` with the new `task_processing_model` value and shows a success indication

#### Scenario: Models endpoint unavailable disables both dropdowns
- **WHEN** the Settings page loads and `GET /api/llm/models` fails
- **THEN** both model dropdowns are disabled and an error message is displayed

### Requirement: MCP server configuration validation
The Settings page SHALL validate the MCP server configuration JSON before saving. The configuration SHALL conform to the format `{"mcpServers": {"<name>": {"url": "<endpoint>", "headers": {…}}}}`. Each server entry MUST have a `url` field (string). The `headers` field is optional (object of string key-value pairs). The Settings page SHALL reject any server entry that contains `command` or `args` fields (STDIO pattern) and display a validation error explaining that only HTTP Streaming MCP servers are supported. The Settings page SHALL reject malformed JSON with a parse error message.

#### Scenario: Valid HTTP Streaming configuration saved
- **WHEN** an admin enters `{"mcpServers": {"argocd": {"url": "http://localhost:4000/argocd/mcp", "headers": {"x-litellm-api-key": "Bearer sk-1234"}}}}` in the MCP configuration field
- **THEN** the configuration is accepted and saved via `PUT /api/settings`

#### Scenario: STDIO configuration rejected
- **WHEN** an admin enters `{"mcpServers": {"local": {"command": "npx", "args": ["-y", "some-mcp-server"]}}}` in the MCP configuration field
- **THEN** the save is blocked and a validation error is displayed: "Only HTTP Streaming MCP servers are supported. Server 'local' uses STDIO transport (command/args) which is not allowed."

#### Scenario: Mixed valid and invalid servers rejected
- **WHEN** an admin enters a configuration with one HTTP Streaming server and one STDIO server
- **THEN** the save is blocked and a validation error identifies the STDIO server by name

#### Scenario: Missing url field rejected
- **WHEN** an admin enters `{"mcpServers": {"test": {"headers": {"key": "value"}}}}` (no `url` field)
- **THEN** the save is blocked and a validation error is displayed: "Server 'test' is missing required 'url' field."

#### Scenario: Invalid JSON rejected
- **WHEN** an admin enters malformed JSON in the MCP configuration field
- **THEN** the save is blocked and a validation error is displayed indicating the JSON is invalid

The Settings page SHALL display an additional section "Task Archiving" containing a number input labelled "Archive after (days)" for configuring how many days completed tasks remain on the board before being auto-archived. The input SHALL load its current value from `GET /api/settings` (key `archive_after_days`). If no `archive_after_days` setting exists, the input SHALL default to `3`. A "Save" button SHALL send the updated value via `PUT /api/settings` with `{"archive_after_days": <number>}`.

#### Scenario: Load default archive interval
- **WHEN** the Settings page loads and no `archive_after_days` setting exists
- **THEN** the "Archive after (days)" input displays `3`

#### Scenario: Load existing archive interval
- **WHEN** the Settings page loads and `archive_after_days` is set to `7`
- **THEN** the "Archive after (days)" input displays `7`

#### Scenario: Save archive interval
- **WHEN** the admin changes the archive interval to `5` and clicks "Save"
- **THEN** the frontend sends `PUT /api/settings` with `{"archive_after_days": 5}` and displays a success indication

### Requirement: Archived Tasks navigation link

The header user dropdown SHALL include an "Archived Tasks" link that navigates to `/archived`. The link SHALL be visible to all authenticated users (viewer, editor, admin), positioned above the Settings link in the dropdown.

#### Scenario: Viewer sees Archived Tasks link
- **WHEN** a viewer opens the user dropdown in the header
- **THEN** the dropdown includes an "Archived Tasks" link but not a "Settings" link

#### Scenario: Admin sees both links
- **WHEN** an admin opens the user dropdown in the header
- **THEN** the dropdown includes both "Archived Tasks" and "Settings" links

#### Scenario: Archived Tasks link navigates to page
- **WHEN** a user clicks the "Archived Tasks" link in the dropdown
- **THEN** the browser navigates to `/archived`

The "LLM Models" section SHALL display a third dropdown labelled "Transcription Model" for selecting the speech-to-text model. The dropdown SHALL be populated by calling `GET /api/llm/transcription-models` (NOT the generic `/api/llm/models` endpoint) which returns only models with audio transcription capability. The current selection SHALL be loaded from `GET /api/settings` (key `transcription_model`). If no `transcription_model` setting exists, the dropdown SHALL show a placeholder "Select a model to enable voice input" with no model selected. Selecting a model SHALL immediately save the choice via `PUT /api/settings` with `{"transcription_model": "<selected>"}`.

The dropdown SHALL also include a "Disabled" option that, when selected, removes the `transcription_model` setting (sends `PUT /api/settings` with `{"transcription_model": null}`), disabling voice input for all users.

#### Scenario: No transcription model selected (default)
- **WHEN** the Settings page loads and no `transcription_model` setting exists
- **THEN** the "Transcription Model" dropdown shows placeholder "Select a model to enable voice input" with no model selected

#### Scenario: Transcription model selected
- **WHEN** the Settings page loads and the `transcription_model` setting is `groq/whisper-large-v3`
- **THEN** the "Transcription Model" dropdown shows `groq/whisper-large-v3` as selected

#### Scenario: Select transcription model
- **WHEN** the admin selects `whisper-1` from the "Transcription Model" dropdown
- **THEN** the frontend sends `PUT /api/settings` with `{"transcription_model": "whisper-1"}` and shows a success indication

#### Scenario: Disable transcription
- **WHEN** the admin selects "Disabled" from the "Transcription Model" dropdown
- **THEN** the frontend sends `PUT /api/settings` with `{"transcription_model": null}` to remove the setting, disabling voice input

#### Scenario: Only transcription-capable models shown
- **WHEN** the Settings page loads the transcription model dropdown
- **THEN** only models with `mode: audio_transcription` from the LiteLLM proxy are shown (not general chat or embedding models)

#### Scenario: No transcription models available
- **WHEN** `GET /api/llm/transcription-models` returns an empty array
- **THEN** the dropdown is disabled and shows "No transcription models available"

#### Scenario: Transcription models endpoint unavailable
- **WHEN** `GET /api/llm/transcription-models` fails
- **THEN** the dropdown is disabled and an error message is displayed

### Requirement: MCP API Key display section

The Settings page SHALL display an "MCP API Key" section showing the API key loaded from `GET /api/settings` (key `mcp_api_key`). The API key SHALL be masked by default (displayed as `••••••••••••••••` or similar) with a "Reveal" toggle button to show the full key. A "Copy" button SHALL copy the full API key to the clipboard regardless of whether it is currently revealed. After copying, the button SHALL briefly show "Copied!" feedback.

#### Scenario: API key displayed masked

- **WHEN** the Settings page loads and an `mcp_api_key` exists
- **THEN** the "MCP API Key" section displays the key as masked text with "Reveal" and "Copy" buttons

#### Scenario: Reveal API key

- **WHEN** the admin clicks the "Reveal" button
- **THEN** the full API key is displayed in plain text and the button changes to "Hide"

#### Scenario: Hide API key

- **WHEN** the admin clicks the "Hide" button while the key is revealed
- **THEN** the key is masked again and the button changes back to "Reveal"

#### Scenario: Copy API key

- **WHEN** the admin clicks the "Copy" button
- **THEN** the full API key is copied to the clipboard and the button briefly shows "Copied!"

#### Scenario: No API key exists

- **WHEN** the Settings page loads and no `mcp_api_key` exists in the settings response
- **THEN** the section displays a message like "No API key generated. Restart the backend to auto-generate one."

### Requirement: Regenerate API key button

The "MCP API Key" section SHALL include a "Regenerate" button. Clicking it SHALL send `POST /api/settings/regenerate-mcp-key`. On success, the section SHALL update to display the new key (masked by default). A confirmation dialog SHALL appear before regenerating to warn that existing MCP clients will need to be reconfigured.

#### Scenario: Regenerate API key

- **WHEN** the admin clicks the "Regenerate" button and confirms the dialog
- **THEN** the frontend sends `POST /api/settings/regenerate-mcp-key`, the new key is displayed (masked), and a success message appears

#### Scenario: Cancel regeneration

- **WHEN** the admin clicks the "Regenerate" button and cancels the confirmation dialog
- **THEN** no API request is made and the current key remains unchanged

#### Scenario: Regeneration error

- **WHEN** the admin confirms regeneration and the API request fails
- **THEN** an error message is displayed and the current key remains unchanged

### Requirement: Example MCP configuration block

The "MCP API Key" section SHALL display a pre-formatted example JSON configuration block that users can copy into their AI coding tool configuration. The example SHALL use the current page origin to construct the MCP server URL (e.g., `https://<current-host>/mcp`) and include the API key as a Bearer token in the Authorization header. The example SHALL follow the format:

```json
{
  "mcpServers": {
    "errand": {
      "url": "https://<host>/mcp",
      "headers": {
        "Authorization": "Bearer <api-key>"
      }
    }
  }
}
```

A "Copy" button SHALL copy the entire configuration block to the clipboard.

#### Scenario: Example config with current host

- **WHEN** the Settings page loads at `https://errand.example.com/settings`
- **THEN** the example config block shows `"url": "https://errand.example.com/mcp"`

#### Scenario: Example config includes API key

- **WHEN** the Settings page loads and the API key is `abc123def456`
- **THEN** the example config block shows `"Authorization": "Bearer abc123def456"`

#### Scenario: Copy example config

- **WHEN** the admin clicks the "Copy" button on the example config block
- **THEN** the entire JSON configuration is copied to the clipboard with "Copied!" feedback

#### Scenario: Config updates after key regeneration

- **WHEN** the admin regenerates the API key
- **THEN** the example configuration block immediately updates to include the new key

### Requirement: Git SSH Key section displays public key

The Settings page SHALL display a "Git SSH Key" section containing a read-only display of the SSH public key loaded from `GET /api/settings` (key `ssh_public_key`). The public key SHALL be displayed in a monospace font code block. A "Copy" button SHALL copy the full public key to the clipboard. After copying, the button SHALL briefly show "Copied!" feedback. Below the public key, the section SHALL display a help text: "Add this key as a deploy key to your Git repositories. Enable write access if you want the agent to push changes."

#### Scenario: Public key displayed

- **WHEN** the Settings page loads and an `ssh_public_key` exists
- **THEN** the "Git SSH Key" section displays the public key in a monospace code block with a "Copy" button

#### Scenario: Copy public key

- **WHEN** the admin clicks the "Copy" button next to the public key
- **THEN** the full public key is copied to the clipboard and the button briefly shows "Copied!"

#### Scenario: No SSH key exists

- **WHEN** the Settings page loads and no `ssh_public_key` exists in the settings response
- **THEN** the section displays a message "No SSH key generated. Restart the backend to auto-generate one."

### Requirement: Regenerate SSH keypair button

The "Git SSH Key" section SHALL include a "Regenerate" button. Clicking it SHALL display a confirmation dialog warning that existing deploy keys configured with the current public key will stop working. On confirmation, the button SHALL send `POST /api/settings/regenerate-ssh-key`. On success, the section SHALL update to display the new public key.

#### Scenario: Regenerate SSH keypair

- **WHEN** the admin clicks the "Regenerate" button and confirms the dialog
- **THEN** the frontend sends `POST /api/settings/regenerate-ssh-key`, the new public key is displayed, and a success message appears

#### Scenario: Cancel regeneration

- **WHEN** the admin clicks the "Regenerate" button and cancels the confirmation dialog
- **THEN** no API request is made and the current key remains unchanged

#### Scenario: Regeneration error

- **WHEN** the admin confirms regeneration and the API request fails
- **THEN** an error message is displayed and the current key remains unchanged

### Requirement: Git SSH hosts configuration

The "Git SSH Key" section SHALL include an editable list of git repository hosts that should use SSH authentication. The list SHALL load its current value from `GET /api/settings` (key `git_ssh_hosts`). If no `git_ssh_hosts` setting exists, the list SHALL default to `["github.com", "bitbucket.org"]`. Each host entry SHALL have a remove button. An "Add Host" input and button SHALL allow adding new hostnames. A "Save" button SHALL send the updated list via `PUT /api/settings` with `{"git_ssh_hosts": [<hosts>]}`.

#### Scenario: Load existing hosts

- **WHEN** the Settings page loads and `git_ssh_hosts` is set to `["github.com", "gitlab.com"]`
- **THEN** the host list displays "github.com" and "gitlab.com" with remove buttons

#### Scenario: Load default hosts

- **WHEN** the Settings page loads and no `git_ssh_hosts` setting exists
- **THEN** the host list displays "github.com" and "bitbucket.org"

#### Scenario: Add a host

- **WHEN** the admin types "gitlab.com" in the add host input and clicks "Add Host"
- **THEN** "gitlab.com" appears in the host list

#### Scenario: Remove a host

- **WHEN** the admin clicks the remove button next to "bitbucket.org"
- **THEN** "bitbucket.org" is removed from the host list

#### Scenario: Save hosts

- **WHEN** the admin modifies the host list and clicks "Save"
- **THEN** the frontend sends `PUT /api/settings` with `{"git_ssh_hosts": [<updated-hosts>]}` and displays a success indication

#### Scenario: Duplicate host prevented

- **WHEN** the admin tries to add "github.com" but it already exists in the list
- **THEN** the host is not added and a validation message is displayed

#### Scenario: Empty hostname prevented

- **WHEN** the admin clicks "Add Host" with an empty input
- **THEN** no host is added

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

### Requirement: Skills Repository configuration section
The Settings page SHALL display a "Skills Repository" section in the Agent Configuration group. The section SHALL contain three input fields: a text input labelled "Repository URL" for the git clone URL, a text input labelled "Branch" with placeholder "default" for the optional branch name, and a text input labelled "Skills Path" with placeholder "/" for the optional base path within the repository. A "Save" button SHALL send the values via `PUT /api/settings` with `{"skills_git_repo": {"url": "<value>", "branch": "<value>", "path": "<value>"}}`. Empty branch and path fields SHALL be omitted from the saved JSON (not sent as empty strings). The section SHALL load its current values from `GET /api/settings` (key `skills_git_repo`) on mount.

#### Scenario: Load existing git repo configuration
- **WHEN** the Settings page loads and `skills_git_repo` is `{"url": "git@github.com:org/skills.git", "branch": "main", "path": "skills"}`
- **THEN** the Repository URL input shows `git@github.com:org/skills.git`, the Branch input shows `main`, and the Skills Path input shows `skills`

#### Scenario: No git repo configured
- **WHEN** the Settings page loads and no `skills_git_repo` setting exists
- **THEN** all three inputs are empty with their respective placeholders

#### Scenario: Save git repo configuration
- **WHEN** the admin enters a repository URL `git@github.com:org/skills.git`, branch `main`, path `skills`, and clicks "Save"
- **THEN** the frontend sends `PUT /api/settings` with `{"skills_git_repo": {"url": "git@github.com:org/skills.git", "branch": "main", "path": "skills"}}` and displays a success indication

#### Scenario: Save with only URL
- **WHEN** the admin enters only a repository URL and leaves branch and path empty, then clicks "Save"
- **THEN** the frontend sends `PUT /api/settings` with `{"skills_git_repo": {"url": "git@github.com:org/skills.git"}}` (branch and path omitted)

#### Scenario: Clear git repo configuration
- **WHEN** the admin clears the repository URL field and clicks "Save"
- **THEN** the frontend sends `PUT /api/settings` with `{"skills_git_repo": null}` to remove the setting

### Requirement: LLM timeout input in LLM Models settings card

The "LLM Models" section on the Task Management settings sub-page SHALL display a number input labelled "LLM Timeout (seconds)" for configuring how many seconds to wait for LLM responses before timing out. The input SHALL load its current value from `GET /api/settings` (key `llm_timeout`). If no `llm_timeout` setting exists, the input SHALL default to `30`. The input SHALL have a minimum value of `1`. The timeout SHALL be saved alongside the model settings when the user clicks the existing "Save" button in the LLM Models card, sent via `PUT /api/settings` with `{"llm_timeout": <number>}`. The input SHALL be included in the dirty-tracking logic so that changing it shows the "Unsaved changes" indicator.

#### Scenario: Load default timeout

- **WHEN** the Settings page loads and no `llm_timeout` setting exists
- **THEN** the "LLM Timeout (seconds)" input displays `30`

#### Scenario: Load existing timeout

- **WHEN** the Settings page loads and `llm_timeout` is set to `60`
- **THEN** the "LLM Timeout (seconds)" input displays `60`

#### Scenario: Save timeout with model settings

- **WHEN** the admin changes the timeout to `120` and clicks "Save" in the LLM Models card
- **THEN** the frontend sends `PUT /api/settings` with `{"llm_timeout": 120}` alongside the model settings and displays a success indication

#### Scenario: Unsaved changes indicator shown

- **WHEN** the admin changes the timeout value without saving
- **THEN** the "Unsaved changes" indicator appears near the Save button

#### Scenario: Minimum value enforced

- **WHEN** the admin enters `0` in the timeout input
- **THEN** the input enforces a minimum of `1`
