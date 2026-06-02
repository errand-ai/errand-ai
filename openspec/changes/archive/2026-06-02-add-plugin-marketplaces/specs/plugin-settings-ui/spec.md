## ADDED Requirements

### Requirement: Plugin Marketplaces section on Agent Configuration page
The frontend Agent Configuration page SHALL include a "Plugin Marketplaces" section that lists every marketplace row returned by `GET /api/marketplaces`. Each row SHALL display: name, source type and URL, enabled toggle, predefined badge (if applicable), last-synced relative timestamp, sync status (ok or error with the error message), and plugin count from the cached manifest. Actions per row: Resync, Edit (name/URL/ref/credential), Remove. Remove SHALL be disabled for predefined rows.

#### Scenario: List marketplaces displayed
- **WHEN** an admin opens Agent Configuration with the predefined Anthropic row plus one custom row
- **THEN** the section shows 2 marketplace rows with their statuses

#### Scenario: Predefined Anthropic row visible but disabled by default
- **WHEN** an admin opens Agent Configuration on a fresh install
- **THEN** the Anthropic marketplace row is visible with its enabled toggle off and the Remove action disabled

#### Scenario: Toggle enable on predefined marketplace
- **WHEN** an admin toggles the Anthropic marketplace to enabled
- **THEN** `PATCH /api/marketplaces/<id>` is called with `{"enabled": true}` and the row reflects the update

#### Scenario: Resync action
- **WHEN** an admin clicks Resync on a marketplace row
- **THEN** `POST /api/marketplaces/<id>/resync` is called and the row shows a loading state until the response returns

### Requirement: Add Marketplace form
The Plugin Marketplaces section SHALL include an "Add Marketplace" button that opens a form with fields for: name (text), source type (radio: GitHub `owner/repo` / Git URL / HTTP JSON / Local path), source URL (text), ref (text, optional, only shown when source type is GitHub or Git), auth credential (dropdown from existing encrypted credentials, optional). On submit, `POST /api/marketplaces` SHALL be called. Validation failures SHALL surface as an error toast.

#### Scenario: Add HTTP marketplace with credential
- **WHEN** an admin fills source type=HTTP JSON, source URL=`https://litellm.example/marketplace.json`, selects a credential, and clicks Add
- **THEN** `POST /api/marketplaces` is invoked with `source_type="http"` and the credential ID

#### Scenario: Add GitHub marketplace with ref
- **WHEN** an admin selects source type=GitHub, URL=`acme/plugins`, ref=`main`
- **THEN** `POST /api/marketplaces` is invoked with `source_type="github"` and `ref="main"`

#### Scenario: Duplicate name rejected
- **WHEN** an admin tries to add a marketplace with a name that already exists
- **THEN** an error toast displays the conflict and the form remains open

### Requirement: Plugins section on Agent Configuration page
The Agent Configuration page SHALL include a "Plugins" section listing every plugin row from `GET /api/plugins`. Each plugin SHALL be rendered as an expandable card showing: plugin name, installed version, source (marketplace name or "manual"), enabled toggle, update-available badge (when `update_available=true`) with an Update button, skill count + name list, MCP server count + raw and namespaced name pairs, ignored-artifact summary (type and count), and any skill collision conflicts. The card SHALL have a Remove action.

#### Scenario: Expanded plugin card displays contents
- **WHEN** an admin clicks to expand a plugin row
- **THEN** the card shows the contributed skill names, MCP server name pairs (e.g. `slack` → `slack-toolkit__slack`), and ignored-artifact counts (e.g. "2 hooks, 1 command")

#### Scenario: Update available badge
- **WHEN** a plugin row has `update_available=true`
- **THEN** the card displays a badge showing `latest_available_version` and an Update button

#### Scenario: Update action
- **WHEN** an admin clicks Update on a plugin with an available update
- **THEN** `POST /api/plugins/<id>/update` is called and the badge clears on success

#### Scenario: Toggle plugin enabled
- **WHEN** an admin flips the enabled toggle on a plugin card
- **THEN** `PATCH /api/plugins/<id>` is called with the new `enabled` value

#### Scenario: Skill conflict surfaced
- **WHEN** a plugin's row contains `skill_conflicts: [{"skill": "post-message", "other": "team-chat"}]`
- **THEN** the card highlights the conflicting skill with a warning indicator and the name of the colliding plugin

### Requirement: Install plugin from marketplace dialog
The Plugins section SHALL include an "Install from Marketplace" button that opens a dialog containing: marketplace dropdown (populated from enabled marketplaces), plugin dropdown (populated from the selected marketplace's `GET /api/marketplaces/<id>/plugins`), version dropdown (populated from the chosen plugin's available versions, defaulting to the latest). On submit, `POST /api/plugins` SHALL be called with `{marketplace_id, plugin_name, version}`. The dialog SHALL show a preview of the plugin's skills, MCP servers, and any unsupported source flag before confirm.

#### Scenario: Install marketplace plugin
- **WHEN** an admin selects marketplace=`acme-public`, plugin=`slack-toolkit`, version=`1.2.0` and confirms
- **THEN** `POST /api/plugins` is invoked with the three fields and the dialog closes on success

#### Scenario: Preview before install
- **WHEN** the admin selects a plugin in the dropdown
- **THEN** the dialog displays the plugin's listed skills, MCP servers, and any unsupported flags

#### Scenario: Unsupported plugin install blocked
- **WHEN** the chosen plugin has an unsupported source flag (e.g. npm)
- **THEN** the Install button is disabled with a tooltip explaining the limitation

### Requirement: Install plugin manually dialog
The Plugins section SHALL include an "Install Manually" button that opens a dialog with fields for: source type (radio: GitHub `owner/repo` / Git URL), source URL (text), ref or version (text, optional), auth credential (dropdown, optional). On submit, `POST /api/plugins` SHALL be called with the direct source descriptor. The dialog SHALL surface install errors as toasts and stay open.

#### Scenario: Manual install via GitHub shorthand
- **WHEN** an admin enters source type=GitHub, source URL=`acme/research-pack`, ref=`v0.5.0`
- **THEN** `POST /api/plugins` is called with `{source_type: "github", source_url: "acme/research-pack", ref: "v0.5.0"}`

#### Scenario: Install error surfaced
- **WHEN** the manual install fails (e.g. invalid plugin source)
- **THEN** an error toast displays the message and the dialog remains open for correction

### Requirement: Plugin source badges in existing Skills and MCP Servers tabs
The existing Skills tab and MCP Servers tab on the Agent Configuration page SHALL display plugin-sourced entries (read-only) with a "from plugin: `<plugin_name>`" badge. Plugin entries SHALL NOT be editable from those tabs (admins manage them via the Plugins section).

#### Scenario: Plugin skill shown in Skills tab
- **WHEN** a plugin `slack-toolkit` contributes a `post-message` skill
- **THEN** the Skills tab lists `post-message` with a "from plugin: slack-toolkit" badge and no Edit action

#### Scenario: Plugin MCP shown in MCP Servers tab
- **WHEN** a plugin `slack-toolkit` namespaces an `slack` MCP server as `slack-toolkit__slack`
- **THEN** the MCP Servers tab lists `slack-toolkit__slack` with a "from plugin: slack-toolkit" badge

### Requirement: Polling interval setting exposed
The Agent Configuration page SHALL include a form control for the `plugin_poll_interval_seconds` setting, validated as a non-negative integer. A value of `0` SHALL be presented in the UI as "Polling disabled".

#### Scenario: Set interval to 4 hours
- **WHEN** an admin enters `14400` and saves
- **THEN** `PUT /api/settings` is called with `{plugin_poll_interval_seconds: 14400}`

#### Scenario: Disable polling
- **WHEN** an admin sets the value to `0`
- **THEN** the UI displays "Polling disabled" and the setting is persisted as `0`
