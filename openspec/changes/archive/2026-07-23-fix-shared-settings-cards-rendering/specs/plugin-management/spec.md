## MODIFIED Requirements

### Requirement: Plugin list API
The backend SHALL expose `GET /api/plugins` returning all installed plugins with their `id`, `plugin_name`, `marketplace_id` (or `null`), `installed_version`, `latest_available_version`, `enabled`, skill name list (from manifest), MCP server name list with both raw and namespaced names, `ignored_artifacts` summary, and any `skill_conflicts` from the last worker resolution.

The endpoint SHALL degrade gracefully when a plugin's on-disk state is missing or unreadable: a missing installed-plugin directory, manifest, or referenced path MUST NOT cause the request to fail. The endpoint MUST NOT return HTTP 500 due to such state; it SHALL still return HTTP 200. A plugin whose on-disk content cannot be read (or whose serialization otherwise fails) SHALL still appear in the listing as a degraded entry (empty contributions) rather than being dropped, and SHALL log a warning. The degraded entry MUST carry a `load_error` field, which MUST be a sanitized, stable message (e.g. the error class name) and MUST NOT expose the raw exception string or internal filesystem paths — full detail belongs only in the server logs.

#### Scenario: List installed plugins
- **WHEN** an admin calls `GET /api/plugins` with two installed plugins
- **THEN** the response is a JSON array of 2 plugin objects with the fields above

#### Scenario: Plugin contributing nothing
- **WHEN** a plugin defines no skills and no MCP servers
- **THEN** the plugin still appears in the list with empty skill/MCP name lists

#### Scenario: Missing installed-plugin directory does not 500
- **WHEN** an admin calls `GET /api/plugins` and one plugin's installed directory or manifest path (e.g. `.../plugins/installed/<marketplace>/<plugin>/latest`) does not exist on disk
- **THEN** the endpoint returns HTTP 200 (not 500)
- **AND** the readable plugins are returned
- **AND** a warning is logged for the missing/degraded plugin
- **AND** the degraded plugin's `load_error` field is a sanitized message (error class only) that does not contain the raw filesystem path
