## Context

The settings page currently renders all settings components on a single scrolling page, grouped under three h3 headers (Agent Configuration, Task Management, Integrations & Security). As the application grows, this layout becomes unwieldy. The user wants a sidebar navigation pattern similar to Claude.ai's settings page, where each group becomes its own sub-page.

Current structure:
- `SettingsPage.vue` — single page rendering all 8+ settings components
- `router/index.ts` — single `/settings` route
- All settings components exist and are functional; they just need to be reorganized

## Goals / Non-Goals

**Goals:**
- Split settings into four sub-pages with sidebar navigation: Agent Configuration, Task Management, Security, Integrations
- Maintain all existing functionality — this is a reorganization, not a rewrite
- Reuse all existing settings components without modification (except the label rename)
- Preserve unsaved-changes detection across the active sub-page
- Rename "Task processing model" label to "Default model"
- Move LLM Models from Agent Configuration into Task Management sub-page

**Non-Goals:**
- Redesigning individual settings components
- Changing backend APIs
- Adding new settings or functionality
- Mobile-responsive sidebar (keep desktop-first, sidebar can stack on mobile later)

## Decisions

### 1. Vue Router nested routes vs. component-level tab switching

**Decision: Vue Router nested routes**

Use nested child routes under `/settings` so each sub-page has its own URL (e.g., `/settings/agent`, `/settings/tasks`). This enables direct linking to specific settings sub-pages and preserves browser back/forward navigation.

Alternative considered: A reactive `activeTab` ref with `v-if` switching — simpler but loses URL-addressable sub-pages and doesn't scale well for potential deeper nesting.

### 2. Sub-page component structure

**Decision: Four dedicated view components**

Create four new sub-page components in `frontend/src/pages/settings/`:
- `AgentConfigurationPage.vue` — SystemPromptSettings, SkillsSettings, SkillsRepoSettings, McpServerConfigSettings
- `TaskManagementPage.vue` — LlmModelSettings, TaskManagementSettings
- `SecurityPage.vue` — GitSshKeySettings, McpApiKeySettings
- `IntegrationsPage.vue` — PlatformSettings

Each sub-page component simply arranges the existing settings components with appropriate spacing. The existing components are reused as-is.

### 3. SettingsPage.vue as layout shell

**Decision: SettingsPage.vue becomes a layout with sidebar + `<router-view>`**

`SettingsPage.vue` will render:
- A sidebar with navigation links (left column)
- A `<router-view>` for the active sub-page (right column)

The sidebar uses `<router-link>` elements with active class styling. The page heading "Settings" remains at the top of the content area, above the sidebar/content layout, consistent with the current design.

### 4. Settings data loading

**Decision: Keep loading in individual components**

Each settings component already handles its own data loading via `useApi`. No change needed — when a sub-page mounts, its child components load their data. This avoids a centralized settings store and keeps the change minimal.

### 5. Unsaved changes detection scope

**Decision: Track unsaved changes per sub-page only**

The `beforeunload` guard and dirty tracking will apply to the currently active sub-page's components. When switching sub-pages via sidebar, if the current sub-page has unsaved changes, use Vue Router's `beforeRouteLeave` guard to warn the user. This replaces the current page-level `beforeunload` approach for intra-settings navigation while keeping `beforeunload` for navigating away from settings entirely.

### 6. Default route and redirect

**Decision: `/settings` redirects to `/settings/agent`**

Navigating to `/settings` will redirect to `/settings/agent` (Agent Configuration). This ensures the sidebar always has an active item and users land on a meaningful page.

### 7. Sidebar styling

**Decision: Vertical nav list with active indicator**

The sidebar will use a simple vertical list of text links with:
- Active: `bg-gray-100 text-gray-900 font-medium rounded-md` (pill-style highlight)
- Inactive: `text-gray-600 hover:text-gray-900 hover:bg-gray-50`
- Fixed width sidebar (~200px), content area fills remaining space
- Sidebar is sticky so it remains visible while scrolling content

This matches the Claude.ai reference screenshot pattern and aligns with the existing `app-navigation` pill-style active state.

## Risks / Trade-offs

- **Bookmark breakage**: Existing bookmarks to `/settings` will redirect to `/settings/agent` — acceptable since `/settings` wasn't deep-linked to specific sections before.
- **Unsaved changes on sub-page switch**: If a user has unsaved changes and clicks a different sidebar item, they'll get a warning. This is slightly more friction than the current single-page but prevents accidental data loss.
- **Test updates**: Frontend tests that navigate to `/settings` will need updating to account for the redirect to `/settings/agent`. Existing component-level tests should pass without changes.
