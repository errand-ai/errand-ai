## ADDED Requirements

### Requirement: Claude MCP settings generation
When TaskManager prepares a claude-task-runner container, it SHALL generate a `~/.claude/settings.json` file containing the user's configured MCP servers translated to Claude Code format. This file SHALL be injected into the container alongside the existing `/workspace/mcp.json`.

#### Scenario: MCP servers translated to Claude format
- **WHEN** TaskManager prepares a claude-task-runner container with MCP servers "playwright" (url: http://playwright:3000/mcp) and "hindsight" (url: https://hindsight.example.com/mcp/bank/)
- **THEN** the container contains `~/.claude/settings.json` with:
  ```json
  {
    "mcpServers": {
      "playwright": { "url": "http://playwright:3000/mcp" },
      "hindsight": { "url": "https://hindsight.example.com/mcp/bank/" }
    }
  }
  ```

#### Scenario: MCP server with auth headers
- **WHEN** an MCP server has `auth_header: "Bearer <token>"`
- **THEN** the Claude settings entry includes `"headers": {"Authorization": "Bearer <token>"}`

#### Scenario: No MCP servers configured
- **WHEN** the resolved MCP server list is empty
- **THEN** `~/.claude/settings.json` contains `{"mcpServers": {}}`

#### Scenario: Profile filters MCP servers
- **WHEN** the Task Profile has `mcp_servers: ["playwright"]` and global config has "playwright" and "hindsight"
- **THEN** only "playwright" appears in `~/.claude/settings.json`

### Requirement: Claude config directory creation
The TaskManager SHALL ensure the `~/.claude/` directory exists in the container with appropriate permissions (mode 700) before writing `settings.json`. For Docker runtime, this SHALL be done via the file injection mechanism. The directory path SHALL be `/home/nonroot/.claude/` matching the container's nonroot user home.

#### Scenario: Config directory created
- **WHEN** TaskManager injects files into a claude-task-runner container
- **THEN** `/home/nonroot/.claude/settings.json` exists with mode 600

### Requirement: Claude config not generated for default images
The Claude MCP settings file SHALL only be generated when the container image is the claude-task-runner variant. Default task-runner containers SHALL NOT receive `~/.claude/settings.json`.

#### Scenario: Default image skips Claude config
- **WHEN** TaskManager prepares a default task-runner container
- **THEN** no `~/.claude/settings.json` is injected
