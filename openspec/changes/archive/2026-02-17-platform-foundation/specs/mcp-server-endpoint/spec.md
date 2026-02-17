## MODIFIED Requirements

### Requirement: MCP endpoint listed in tool discovery

- **WHEN** a client sends a `tools/list` request to `/mcp`
- **THEN** the response includes the tools: `new_task`, `task_status`, `task_output`, `post_tweet`

The `post_tweet` tool SHALL delegate to the platform registry's `TwitterPlatform.post()` method instead of calling the Tweepy API directly. The tool's interface (parameters, return format) SHALL remain unchanged.

#### Scenario: post_tweet delegates to platform abstraction
- **WHEN** a client calls `post_tweet` with a valid message
- **THEN** the MCP tool calls `registry.get("twitter").post(message)` and returns the result

#### Scenario: post_tweet with no platform configured
- **WHEN** a client calls `post_tweet` and the Twitter platform has no credentials (DB or env var)
- **THEN** the tool returns "Error: Twitter API credentials not configured"
