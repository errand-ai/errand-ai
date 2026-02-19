## MODIFIED Requirements

### Requirement: MCP server identity
The MCP server display name SHALL be "Errand" (changed from "Content Manager").

#### Scenario: Server name in tool listing
- **WHEN** a client sends a `tools/list` request to `/mcp`
- **THEN** the server identifies itself as "Errand"
