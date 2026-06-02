## ADDED Requirements

### Requirement: Plugin multi-select in profile editor
The profile editor form (Add Profile and Edit Profile) SHALL include a "Plugins" multi-select control populated from `GET /api/plugins` filtered to `enabled=true` rows. The control SHALL save the selected plugin IDs into the profile's `enabled_plugins` field. The control SHALL render each plugin row with its name, version, and an expandable preview listing the plugin's contributed skill names and namespaced MCP server names.

#### Scenario: Plugins multi-select populated
- **WHEN** an admin opens the profile editor with 3 enabled plugins
- **THEN** the Plugins control lists 3 selectable plugins

#### Scenario: Disabled plugins excluded
- **WHEN** an admin opens the profile editor and one plugin row has `enabled=false`
- **THEN** that plugin is not shown in the Plugins control

#### Scenario: Preview shows contributed skills and MCPs
- **WHEN** an admin expands a plugin row in the editor
- **THEN** the row displays the plugin's contributed skill names and MCP server name pairs (raw → namespaced)

#### Scenario: Select plugins saves array
- **WHEN** an admin checks two plugins and clicks Save
- **THEN** the profile is saved with `enabled_plugins` containing the two plugin UUIDs

#### Scenario: Editing profile loads existing enabled_plugins
- **WHEN** an admin edits a profile with `enabled_plugins = ["abc-123"]`
- **THEN** the Plugins control has the matching plugin pre-selected

#### Scenario: Editing profile with stale plugin reference
- **WHEN** an admin edits a profile whose `enabled_plugins` references a plugin ID that no longer exists
- **THEN** the editor displays a "removed plugin" indicator for that ID with an option to clear it from the list

### Requirement: Profile summary card lists enabled plugin count
Each profile card on the profile settings page SHALL include an "Plugins: N" entry in its summary, where N is the count of plugin IDs in `enabled_plugins`. When `enabled_plugins` is null or empty, the card SHALL display "Plugins: None".

#### Scenario: Profile with 2 plugins
- **WHEN** a profile has `enabled_plugins = ["id1", "id2"]`
- **THEN** the card summary includes "Plugins: 2"

#### Scenario: Profile with no plugins
- **WHEN** a profile has `enabled_plugins = null`
- **THEN** the card summary includes "Plugins: None"
