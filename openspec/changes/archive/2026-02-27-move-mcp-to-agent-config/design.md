## Context

The LiteLLM MCP Servers settings section (`LitellmMcpSettings.vue`) currently renders on the Integrations sub-page alongside platform credentials. With the addition of Task Profiles — which reference LiteLLM MCP servers per-profile — the section is more naturally grouped with other agent configuration concerns (system prompt, skills, MCP server config).

The component is self-contained: it fetches its own data from `GET /api/litellm/mcp-servers`, manages its own state, and saves via the shared `saveSettings` inject. Moving it requires only changing which page imports it.

## Goals / Non-Goals

**Goals:**
- Move the LiteLLM MCP Servers section to the bottom of the Agent Configuration page
- Update the two affected specs to reflect the new location
- Keep the Integrations page functional (platform settings only)

**Non-Goals:**
- Refactoring the `LitellmMcpSettings.vue` component itself
- Changing backend API endpoints or settings keys
- Modifying the sidebar navigation or adding/removing sub-pages

## Decisions

**Decision: Place LiteLLM MCP section last on Agent Configuration page**
The section order on Agent Configuration will be: System Prompt → Skills → Skills Repository → MCP Server Configuration → MCP Servers (via LiteLLM). This puts both MCP-related sections adjacent, which is intuitive. The LiteLLM section remains conditionally visible (only when `available: true`).

**Decision: Keep Integrations page with a single section**
Rather than removing the Integrations page entirely, it retains the Platform Settings section. Removing a sub-page would change routes, navigation, and specs — unnecessary churn for this change.

## Risks / Trade-offs

**[Risk: Longer Agent Configuration page]** → The page gains one more section, but it's conditionally rendered and collapses naturally. Acceptable trade-off for better grouping.
