Requested official URL: https://opencode.ai/docs/mcp-servers
Accessed UTC: 2026-10-03T14:55:12.682379+00:00
Title: MCP servers | OpenCode
Retrieval: documentation extraction; excerpt may be abbreviated. Not a runtime test. Trailing whitespace normalized.

# MCP servers | OpenCode
URL: https://opencode.ai/docs/mcp-servers

MCP servers | OpenCode

# MCP servers

Add local and remote MCP tools.

You can add external tools to OpenCode using the Model Context Protocol, or MCP. OpenCode supports both local and remote servers.

Once added, MCP tools are automatically available to the LLM alongside built-in tools.

#### Caveats

When you use an MCP server, it adds to the context. This can quickly add up if you have a lot of tools. So we recommend being careful with which MCP servers you use.

Tip

MCP servers add to your context, so you want to be careful with which ones you enable.

Certain MCP servers, like the GitHub MCP server, tend to add a lot of tokens and can easily exceed the context limit.

## Enable

You can define MCP servers in your OpenCode Config under `mcp`. Add each MCP with a unique name. You can refer to that MCP by name when prompting the LLM.

opencode.jsonc

{

 "$schema": "https://opencode.ai/config.json",

 "mcp": {

 "name-of-mcp-server": {

 // ...

 "enabled": true,

 },

 "name-of-other-mcp-server": {

 // ...

 },

 },

}

You can also disable a server by setting `enabled` to `false`. This is useful if you want to temporarily disable a server without removing it from your config.

### Overriding remote defaults

Organizations can provide default MCP servers via their `.well-known/opencode` endpoint. These servers may be disabled by default, allowing users to opt-in to the ones they need.

To enable a specific server from your organization’s remote config, add it to your local config with `enabled: true`:

opencode.json

{

 "$schema": "https://opencode.ai/config.json",

 "mcp": {

 "jira": {

 "type": "remote",

 "url": "https://jira.example.com/mcp",

 "enabled": true

 }

 }

}

Your local config values override the remote defaults. See config precedence for more details.

## Local

Add local MCP servers using `type` to `"local"` within the MCP object.

opencode.jsonc

{

 "$schema": "https://opencode.ai/config.json",

 "mcp": {

 "my-local-mcp-server": {

 "type": "local",

 // Or ["bun", "x", "my-mcp-command"]

 "command": ["npx", "-y", "my-mcp-command"],

 "enabled": true,

 "environment": {

 "MY_ENV_VAR": "my_env_var_value",

 },

 },

 },

}

The command is how the local MCP server is started. You can also pass in a list of environment variables as well.

For example, here’s how you can add the test `@modelcontextprotocol/server-everything` MCP server.

opencode.jsonc

{

 "$schema": "https://opencode.ai/config.json",

 "mcp": {

 "mcp_everything": {

 "type": "local",

 "command": ["npx", "-y", "@modelcontextprotocol/server-everything"],

 },

 },

}

And to use it I can add `use the mcp_everything tool` to my prompts.

use the mcp_everything tool to add the number 3 and 4

#### Options

Here are all the options for configuring a local MCP server.

| Option | Type | Required | Description |
| --- | --- | --- | --- |
| `type` | String | Y | Type of MCP server connection, must be `"local"`. |
| `command` | Array | Y | Command and argume
