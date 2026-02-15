## 1. Foundation: Toast System & Dependencies

- [x] 1.1 Install `vue-sonner` — `cd frontend && npm install vue-sonner`
- [x] 1.2 Mount `<Toaster>` in `App.vue` — import from `vue-sonner`, add `<Toaster position="top-right" />` inside the root template

## 2. App Navigation

- [x] 2.1 Add `<nav>` element in `App.vue` — insert horizontal nav links (Board `/`, Archived `/archived`, Settings `/settings` admin-only) between the logo and user controls, with active route pill highlighting (`bg-gray-100 text-gray-900`)
- [x] 2.2 Simplify user dropdown in `App.vue` — remove "Archived Tasks" and "Settings" items, keep only username display and "Log out" button
- [x] 2.3 Remove `goToArchived()` and `goToSettings()` functions from `App.vue` script (now handled by `<router-link>`)
- [x] 2.4 Write frontend tests for navigation — verify nav links render, active state matches route, Settings hidden for non-admin, dropdown only contains Log out

## 3. Task Card Improvements

- [x] 3.1 Add description preview to `TaskCard.vue` — 2-line truncated preview (`line-clamp-2 text-xs text-gray-500`) below the title, hidden when description is empty
- [x] 3.2 Add repeating category indicator to `TaskCard.vue` — loop/refresh SVG icon + interval text for `category === 'repeating'` tasks
- [x] 3.3 Show `execute_at` on all columns in `TaskCard.vue` — display relative time when `execute_at` is non-null regardless of column (remove Scheduled-only gate)
- [x] 3.4 Add running state indicator to `TaskCard.vue` — pulsing blue dot (`animate-ping`) + "Running..." text when `columnStatus === 'running'`, plus `border-l-2 border-blue-400` accent
- [x] 3.5 Write frontend tests for task card enhancements — verify description preview, repeating indicator, execute_at on non-scheduled columns, running indicator

## 4. Kanban Board Improvements

- [x] 4.1 Increase column minimum width in `KanbanBoard.vue` — change `min-w-[100px]` to `min-w-[240px]`
- [x] 4.2 Replace inline count with pill badge in `KanbanBoard.vue` — replace `(N)` text with `<span class="inline-flex ... rounded-full bg-white/70 ...">N</span>`
- [x] 4.3 Add board-level empty state in `KanbanBoard.vue` — when all columns have zero tasks, show centered icon + "No tasks yet" + guidance text
- [x] 4.4 Remove individual column "No tasks" text in `KanbanBoard.vue` — delete the italic "No tasks" paragraph from empty columns
- [x] 4.5 Add skeleton loading state in `KanbanBoard.vue` — replace "Loading tasks..." text with 6 skeleton columns containing animate-pulse card shapes
- [x] 4.6 Write frontend tests for kanban improvements — verify column width, pill badge, empty state, skeleton loading

## 5. Modal Improvements

- [x] 5.1 Add backdrop-click dismiss to `TaskEditModal.vue` — add `@click.self="onBackdropClick"` on the `<dialog>`, implement dirty-state detection by comparing form values to original props
- [x] 5.2 Add dirty-state confirmation in `TaskEditModal.vue` — show `confirm("Discard unsaved changes?")` when backdrop-clicking or pressing Escape with unsaved changes
- [x] 5.3 Add "Copy raw" button to `TaskOutputModal.vue` — button next to Close, uses `navigator.clipboard.writeText(props.output)`, shows "Copied!" for 2 seconds
- [x] 5.4 Write frontend tests for modal improvements — verify backdrop dismiss, dirty guard, copy-to-clipboard behavior

## 6. Archived Tasks Improvements

- [x] 6.1 Add search input to `ArchivedTasksPage.vue` — text input that filters tasks by title substring (case-insensitive), wired to a `searchQuery` ref
- [x] 6.2 Add status filter dropdown to `ArchivedTasksPage.vue` — select with "All", "Archived", "Deleted" options, wired to a `statusFilter` ref
- [x] 6.3 Add sortable column headers to `ArchivedTasksPage.vue` — clickable Title, Status, Date headers with sort direction indicator, wired to `sortColumn` and `sortDirection` refs
- [x] 6.4 Add `filteredTasks` computed property — chain search filter → status filter → sort, use in `v-for` instead of raw `tasks`
- [x] 6.5 Add result count display — "N tasks" label next to the filter controls
- [x] 6.6 Add empty state to `ArchivedTasksPage.vue` — archive icon + "No archived tasks yet" + guidance text when no tasks exist
- [x] 6.7 Add skeleton loading state to `ArchivedTasksPage.vue` — replace "Loading archived tasks..." with animate-pulse table rows
- [x] 6.8 Write frontend tests for archive improvements — verify search, filter, sort, count, empty state, skeleton loading

## 7. Settings Decomposition

- [x] 7.1 Create `frontend/src/components/settings/` directory
- [x] 7.2 Extract `SystemPromptSettings.vue` — textarea + Save button, receives settings via props, uses toast for feedback
- [x] 7.3 Extract `SkillsSettings.vue` — skill list with add/edit/delete, delete confirmation dialog, empty state, uses toast for feedback
- [x] 7.4 Extract `LlmModelSettings.vue` — three model dropdowns + Save button (no longer auto-save), unsaved-changes indicator
- [x] 7.5 Extract `TaskManagementSettings.vue` — consolidated card with timezone dropdown, archiving days input + Save, runner log level dropdown, all with explicit Save buttons and unsaved-changes indicators, separated by `divide-y`
- [x] 7.6 Extract `McpApiKeySettings.vue` — key display, reveal/copy/regenerate, example config, uses toast for feedback
- [x] 7.7 Extract `GitSshKeySettings.vue` — SSH key management + hosts, uses toast for feedback
- [x] 7.8 Extract `McpServerConfigSettings.vue` — collapsible JSON textarea + Save, uses toast for feedback
- [x] 7.9 Refactor `SettingsPage.vue` as orchestrator — load settings once on mount, render three groups with child components, pass settings and save function as props
- [x] 7.10 Add `beforeunload` guard to `SettingsPage.vue` — register listener when any child section has unsaved changes
- [x] 7.11 Write frontend tests for decomposed settings — verify each component renders correctly, save behavior, unsaved-changes indicators, skill deletion confirmation, beforeunload guard

## 8. Verification

- [x] 8.1 Run full frontend test suite and verify all tests pass
- [x] 8.2 Run full backend test suite and verify all tests pass (no backend changes, but confirm nothing is broken)
- [ ] 8.3 Manual smoke test with `docker compose up --build` — verify navigation, toast notifications, task card enhancements, archive search/filter, settings save patterns, modal behavior
