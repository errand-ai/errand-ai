## Why

A UX review board identified 14 structural usability issues across the application. Navigation is invisible (secondary pages buried in a dropdown), interaction patterns are inconsistent (auto-save vs explicit save, modal dismissal behavior varies), task cards lack visual differentiation (category, recurrence, running state hidden), and the archived tasks page has no search/filter/sort capability. These compound into a disjointed experience that hinders daily use.

## What Changes

- Add a persistent horizontal navigation bar in the App.vue header with active route indicators; shrink user dropdown to just username + log out
- Add backdrop-click dismiss to TaskEditModal with dirty-state confirmation
- Add copy-to-clipboard button for raw output in TaskOutputModal
- Add category/recurrence indicators and description preview to task cards
- Add a pulsing "running" state indicator to task cards in the Running column
- Increase Kanban column minimum width and add pill badge for task counts in column headers
- Add client-side search, status filter, sort, and result count to the Archived Tasks page
- Improve empty states across Kanban board and Archived Tasks with icons and guidance text
- Add skeleton loading placeholders to replace plain "Loading..." text strings
- Add a global toast/notification system (vue-sonner or equivalent) for consistent feedback
- Standardise Settings page save patterns: explicit Save buttons everywhere, unsaved-changes indicators, beforeunload guard
- Decompose SettingsPage.vue into section-level child components
- Consolidate the three single-control Task Management settings cards into one divided card
- Add a confirmation dialog before skill deletion on the Settings page

## Capabilities

### New Capabilities
- `app-navigation`: Persistent header navigation bar with active route indicators, replacing dropdown-based navigation
- `toast-notifications`: Global toast/notification system mounted at App.vue level for transient success/error feedback
- `archive-search-filter`: Client-side search, filter, sort, and result count for the Archived Tasks table

### Modified Capabilities
- `kanban-frontend`: Column min-width increase, pill badge counts in headers, improved empty states, skeleton loading
- `task-edit-modal`: Backdrop-click dismiss with dirty-state confirmation
- `task-output-viewer`: Copy-to-clipboard button for raw output text
- `admin-settings-ui`: Explicit save pattern everywhere, unsaved-changes indicators, beforeunload guard, decompose into child components, consolidate Task Management cards, skill deletion confirmation
- `skill-library`: Add confirmation dialog before skill deletion (UI change only)

## Impact

- **Frontend components**: App.vue (navigation overhaul), KanbanBoard.vue (columns, empty/loading states), TaskCard.vue (category/recurrence/running indicators, description preview), TaskEditModal.vue (backdrop dismiss), TaskOutputModal.vue (copy button), SettingsPage.vue (decomposition into ~7 child components, save pattern standardisation), ArchivedTasksPage.vue (search/filter/sort)
- **New components**: ToastProvider.vue (or vue-sonner integration), ~7 Settings sub-components (SystemPromptSettings, SkillsSettings, LlmModelSettings, TaskManagementSettings, McpApiKeySettings, GitSshKeySettings, McpServerConfigSettings)
- **Dependencies**: Possible addition of `vue-sonner` package for toast notifications
- **Backend**: No changes required (all improvements are frontend-only)
- **Tests**: New frontend tests for toast system, archive filtering, navigation, copy-to-clipboard; updated tests for Settings decomposition
