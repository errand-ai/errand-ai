## ADDED Requirements

### Requirement: LiteLLM MCP server selection is editable and persisted

The "MCP Servers (via LiteLLM)" section SHALL render a toggle per discovered server, reflecting whether that server's alias is present in the `litellm_mcp_servers` setting. The section SHALL track dirty state against the loaded selection and SHALL persist the current selection by sending `litellm_mcp_servers` as an array of alias strings to the settings API. The request SHALL NOT include keys for settings the section does not own.

An empty selection SHALL persist as an empty array, never as `null` and never by omitting the key — otherwise disabling the last enabled server would leave the previous selection in place.

#### Scenario: Enabling a server persists the alias

- **WHEN** an admin toggles "perplexity" on with "argocd" already enabled, and saves
- **THEN** the setting `litellm_mcp_servers` is persisted as `["argocd", "perplexity"]`

#### Scenario: Disabling the last server persists an empty array

- **WHEN** an admin toggles off the only enabled server and saves
- **THEN** the setting `litellm_mcp_servers` is persisted as `[]` and not as `null` or an absent key

#### Scenario: Save sends only the owned key

- **WHEN** an admin changes the selection and saves
- **THEN** the settings request body contains `litellm_mcp_servers` and no other setting key

#### Scenario: Section is clean until the selection changes

- **WHEN** an admin opens Agent Configuration and does not change any toggle
- **THEN** the section reports no unsaved changes

#### Scenario: Changing a toggle marks the section dirty

- **WHEN** an admin toggles a server on or off without saving
- **THEN** the section reports unsaved changes

#### Scenario: Successful save clears dirty state

- **WHEN** an admin saves a changed selection and the request succeeds
- **THEN** the section reports no unsaved changes and the saved selection becomes the new baseline

#### Scenario: Failed save keeps the change pending

- **WHEN** an admin saves a changed selection and the request fails
- **THEN** the section still reports unsaved changes so the edit is not silently discarded

#### Scenario: Discard restores the loaded selection

- **WHEN** an admin toggles two servers and then discards
- **THEN** every toggle returns to its loaded state and the section reports no unsaved changes
