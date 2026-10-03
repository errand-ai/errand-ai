Requested official URL: https://opencode.ai/docs/cli
Accessed UTC: 2026-10-03T14:54:58.213075+00:00
Title: CLI | OpenCode
Retrieval: documentation extraction; excerpt may be abbreviated. Not a runtime test. Trailing whitespace normalized.

# CLI
But it also accepts commands as documented on this page. This allows you to interact with OpenCode programmatically.
Terminal window
```
opencode run "Explain how closures work in JavaScript"
```

...

## Commands
### agent
Manage agents for OpenCode.
Terminal window
```
opencode agent [command]
```

#### create
Create a new agent with custom configuration.
Terminal window
```
opencode agent create
```
This command will guide you through creating a new agent with a custom system prompt and permission configuration. Anything you don’t allow is denied in the generated agent’s frontmatter.

#### Flags
| Flag | Short | Description |
| `--path` | Directory to write the agent file to (defaults to global or `.opencode/agent` based on the prompt) |  |
| `--description` | What the agent should do |  |
| `--mode` | Agent mode: `all` , `primary` , or `subagent` |  |
| `--permissions` | Comma-separated list of permissions to allow (default: all). Available: `bash` , `read` , `edit` , `glob` , `grep` , `webfetch` , `task` , `todowrite` , `websearch` , `lsp` , `skill` . Anything omitted is denied. Alias: `--tools` |  |
| `--model` | `-m` | Model to use, in `provider/model` format |

...

### attach
```
# Start the backend server for web/mobile access opencode web --port 4096 --hostname 0.0.0.0 # In another terminal, attach the TUI to the running backend opencode attach http://10.20.30.40:4096
```

#### Flags
| Flag | Short | Description |
| `--dir` | Working directory to start TUI in |  |
| `--continue` | `-c` | Continue the last session |
| `--session` | `-s` | Session ID to continue |
| `--fork` | Fork the session when continuing (use with `--continue` or `--session` ) |  |
| `--password` | `-p` | Basic auth password (defaults to `OPENCODE_SERVER_PASSWORD` ) |
| `--username` | `-u` | Basic auth username (defaults to `OPENCODE_SERVER_USERNAME` or `opencode` ) |

...

### mcp
Manage Model Context Protocol servers.
Terminal window
```
opencode mcp [command]
```

#### add
Add an MCP server to your configuration.
Terminal window
```
opencode mcp add
```
This command will guide you through adding either a local or remote MCP server.

...

### models
List all available models from configured providers.
Terminal window
```
opencode models [provider]
```
This command displays all models available across your configured providers in the format `provider/model` .

...

### serve
Start a headless OpenCode server for API access. Check out the [server docs](https://opencode.ai/docs/server) for the full HTTP interface.
Terminal window
```
opencode serve
```

...

### web
Start a headless OpenCode server with a web interface.
Terminal window
```
opencode web
```
This starts an HTTP server and opens a web browser to access OpenCode through a web interface. Set `OPENCODE_SERVER_PASSWORD` to enable HTTP basic auth (username defaults to `opencode` ).

...

### acp
Start an ACP (Agent Client Protocol) server.
Terminal window
```
opencode acp
```
This command starts an ACP server that communicates via stdin/stdout using nd-JSON.

...

### upgrade
Updates opencode to the latest version or a specific version.
Terminal window
```
opencode upgrade [target]
```
To upgrade to the latest version.
Terminal window
```
opencode upgrade
```
To upgrade to a specific version.
Terminal window
```
opencode upgrade v0.1.48
```

#### Flags
| Flag | Short | Description |
| `--method` | `-m` | The installation method that was used; curl, npm, pnpm, bun, brew |
