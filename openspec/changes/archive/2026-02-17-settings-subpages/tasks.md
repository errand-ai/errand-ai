## 1. Router and Layout

- [x] 1.1 Update `frontend/src/router/index.ts`: replace the single `/settings` route with a parent route containing four child routes (`/settings/agent`, `/settings/tasks`, `/settings/security`, `/settings/integrations`), a redirect from `/settings` to `/settings/agent`, and a catch-all redirect for unknown sub-pages
- [x] 1.2 Refactor `frontend/src/pages/SettingsPage.vue` from a single-page layout to a two-column layout with sidebar navigation (left) and `<router-view>` (right); keep the "Settings" heading at the top

## 2. Sub-page Components

- [x] 2.1 Create `frontend/src/pages/settings/AgentConfigurationPage.vue` rendering SystemPromptSettings, SkillsSettings, SkillsRepoSettings, and McpServerConfigSettings
- [x] 2.2 Create `frontend/src/pages/settings/TaskManagementPage.vue` rendering LlmModelSettings and TaskManagementSettings
- [x] 2.3 Create `frontend/src/pages/settings/SecurityPage.vue` rendering GitSshKeySettings and McpApiKeySettings
- [x] 2.4 Create `frontend/src/pages/settings/IntegrationsPage.vue` rendering PlatformSettings

## 3. Label and Grouping Changes

- [x] 3.1 Rename "Task Processing Model" label to "Default Model" in `LlmModelSettings.vue`

## 4. Navigation Active State

- [x] 4.1 Update App.vue header navigation so the "Settings" link is highlighted as active when the route starts with `/settings` (matching any sub-page)

## 5. Unsaved Changes Guards

- [x] 5.1 Add `onBeforeRouteLeave` guard to each sub-page component to warn when child components have unsaved changes, preventing accidental data loss on sidebar navigation
- [x] 5.2 Ensure `beforeunload` listener is active on each sub-page when any child has unsaved changes

## 6. Tests

- [x] 6.1 Update existing frontend tests that reference `/settings` to account for the redirect to `/settings/agent` and sub-page routing
- [x] 6.2 Add tests for settings sidebar navigation: renders all links, highlights active link, navigates between sub-pages
- [x] 6.3 Add tests for each sub-page component: renders the correct settings components
- [x] 6.4 Run full frontend test suite and fix any failures
