## Why

The settings page has grown to include agent configuration, task management, security keys, and platform integrations all on a single scrolling page. As more settings and integrations are added, this becomes harder to navigate. Splitting settings into sub-pages with sidebar navigation improves usability and creates a scalable structure for future additions.

## What Changes

- Replace the single-page settings layout with a sidebar navigation + content area pattern (similar to Claude.ai settings)
- Group settings into four sub-pages:
  - **Agent Configuration**: system prompt, skills, skills repository, MCP server configuration
  - **Task Management**: default model (renamed from "Task processing model"), title generation model, transcription model, timezone, archive-after-days, task runner log level
  - **Security**: Git SSH key, MCP API key
  - **Integrations**: platform credentials and connections
- Rename "Task processing model" label to "Default model" to support future multi-model configuration
- Add Vue Router nested routes under `/settings/` for each sub-page
- Default to the first sub-page (Agent Configuration) when navigating to `/settings`

## Capabilities

### New Capabilities

- `settings-navigation`: Sidebar navigation component for settings sub-pages with active state highlighting and Vue Router integration

### Modified Capabilities

- `admin-settings-ui`: Settings page restructured from single-page layout to sub-page layout with sidebar navigation; settings grouped into Agent Configuration, Task Management, Security, and Integrations sub-pages
- `app-navigation`: Settings route updated from single `/settings` to `/settings/:subpage` with nested routing

## Impact

- `frontend/src/pages/SettingsPage.vue` — major restructure to sidebar + router-view layout
- `frontend/src/router/index.ts` — add nested routes under `/settings`
- New sub-page view components for each settings group
- `LlmModelSettings.vue` — rename "Task processing model" label to "Default model"
- No backend changes required
- No API changes
- Existing settings components are reused, just reorganized into sub-pages
