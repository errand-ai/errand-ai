Requested official URL: https://hermes-agent.nousresearch.com/docs/user-guide/features/mcp
Accessed UTC: 2026-10-03T14:56:33.038563+00:00
Title: MCP (Model Context Protocol) | Hermes Agent
Retrieval: documentation extraction; excerpt may be abbreviated. Not a runtime test. Trailing whitespace normalized.

# MCP (Model Context Protocol) | Hermes Agent
URL: https://hermes-agent.nousresearch.com/docs/user-guide/features/mcp

MCP (Model Context Protocol) | Hermes Agent

On this page

# MCP (Model Context Protocol)

Python dependency commands on this page use a PM-prepared source checkout. After a dependency change, reactivate the checkout and restart Hermes.

MCP lets Hermes Agent connect to external tool servers so the agent can use tools that live outside Hermes itself — GitHub, databases, file systems, browser stacks, internal APIs, and more.

If you have ever wanted Hermes to use a tool that already exists somewhere else, MCP is usually the cleanest way to do it.

Coming from Claude Code?

The `mcpServers` block in your `~/.claude.json` maps to `mcp_servers` in Hermes' `config.yaml` — and `hermes import-agent claude-code` migrates it (along with skills and instructions) automatically. See Import from Other Agents.

## What MCP gives you​

- Access to external tool ecosystems without writing a native Hermes tool first
- Local stdio servers and remote HTTP MCP servers in the same config
- Automatic tool discovery and registration at startup
- Utility wrappers for MCP resources and prompts when supported by the server
- Per-server filtering so you can expose only the MCP tools you actually want Hermes to see

## Quick start​

1. MCP support ships with the standard install — no extra step needed.
2. Add an MCP server to `~/.hermes/config.yaml`:

mcp_servers:

 filesystem:

 command: "npx"

 args: ["-y", "@modelcontextprotocol/server-filesystem", "/home/user/projects"]

3. Start Hermes:

hermes chat

4. Ask Hermes to use the MCP-backed capability.

For example:

List the files in /home/user/projects and summarize the repo structure.

Hermes will discover the MCP server's tools and use them like any other tool.

## Catalog: one-click install for Nous-approved MCPs​

Hermes ships a curated catalog of MCP servers that Nous staff has reviewed and merged. They're disabled by default — install only what you actually want.

You can also ask in chat: "add the Linear MCP". The agent calls `manage_connections` with an `mcp: true` target and a setup card appears. The card works the same way in the desktop app (a dialog), the terminal UI (`hermes --tui`, a callout above the composer) and the classic CLI (a panel):

1. Fields. If the entry declares setup values, the card shows all of them at once. A plain value is prefilled with its default. A secret is masked. Nothing is saved while you type.
2. Connect or Cancel. Cancel skips that one server; other servers in the same request continue.
3. Authorization. For an OAuth entry the card shows the authorization link. Hermes never opens the browser by itself: click Open in browser on the desktop, or press Enter in the terminal. Over SSH the card tells you how to reach the callback port or paste the redirected URL.
4. Save. Hermes saves the server configuration, the tokens and your setup values together, once the server has accepted the new token and the first connection has returned. If the server rejects the token, or you cancel b
