## Context

The UX review board identified 14 issues across the frontend. All changes are frontend-only — no backend API changes required. The current frontend uses Vue 3 + Tailwind CSS + Pinia, with a monolithic SettingsPage.vue (1,415 lines) and all navigation hidden in a user dropdown.

## Goals / Non-Goals

**Goals:**
- Make all pages discoverable via persistent header navigation
- Standardise interaction patterns (save behavior, modal dismissal, feedback)
- Add visual differentiation to task cards (category, recurrence, running state)
- Make the Archived Tasks page functional at scale (search, filter, sort)
- Reduce SettingsPage.vue complexity through decomposition

**Non-Goals:**
- Backend API changes (all improvements are frontend-only)
- Dark mode support
- Mobile/responsive layout overhaul
- Keyboard shortcuts
- Drag handle refinement for touch devices
- Server-side pagination for archived tasks (client-side filtering is sufficient for current scale)

## Decisions

### D1. Navigation: Header nav bar with route-aware highlighting

Add `<nav>` element in App.vue between logo and user dropdown. Three links: Board (`/`), Archived (`/archived`), Settings (`/settings`, admin-only). Active route gets `bg-gray-100 text-gray-900` pill. Remove navigation items from the user dropdown, keeping only username display and "Log out".

Use `$route.path` matching for active state rather than named routes, since the router already has path-based matching.

### D2. Toast system: vue-sonner

Adopt `vue-sonner` rather than building a custom toast component. It's lightweight (~3KB), follows the Sonner API pattern, and integrates with Tailwind. Mount `<Toaster>` in App.vue. Replace all inline success/error `ref` variables in SettingsPage and its children with `toast.success()` / `toast.error()` calls.

### D3. Settings decomposition: Extract card-level components

Split SettingsPage.vue into an orchestrator (~80 lines) that loads settings once and passes data to child components via props. Each child owns its own save logic and emits toast messages. Components:
- `SystemPromptSettings.vue`
- `SkillsSettings.vue`
- `LlmModelSettings.vue`
- `TaskManagementSettings.vue` (consolidated: timezone + archiving + runner log level)
- `McpApiKeySettings.vue`
- `GitSshKeySettings.vue`
- `McpServerConfigSettings.vue`

Each component receives the full `settings` reactive object and the `saveSettings` function as props (or via a composable).

### D4. Settings save pattern: Explicit save everywhere

Convert the three auto-saving dropdowns (LLM models, timezone, task runner log level) to use explicit Save buttons. Add an `isDirty` computed per section. Show `text-xs text-amber-600 "Unsaved changes"` indicator when dirty. Add a `beforeunload` event listener on SettingsPage when any child section is dirty.

### D5. Modal consistency: Backdrop-click dismiss with dirty guard

Add `@click.self="onBackdropClick"` to TaskEditModal's `<dialog>`. The handler checks a `isDirty` computed (comparing current form values to the original task props). If dirty, show a browser `confirm("Discard unsaved changes?")`. If clean or confirmed, call `onCancel()`.

### D6. Task card enrichment: Category indicators and description preview

Add to TaskCard.vue:
- A repeat icon (SVG loop arrow) + interval text for `category === 'repeating'` tasks
- Show `execute_at` relative time on all columns (not just Scheduled)
- A 2-line truncated description preview: `<p class="mt-0.5 text-xs text-gray-500 line-clamp-2">`
- A pulsing blue dot + "Running..." text when `columnStatus === 'running'`

### D7. Column improvements: Wider minimum, pill badge counts

Change column `min-w-[100px]` to `min-w-[240px]`. Replace inline count text with a white pill badge: `rounded-full bg-white/70 px-1.5 text-xs font-medium`.

### D8. Archive search/filter/sort: Client-side computed

Add reactive refs for `searchQuery`, `statusFilter`, `sortColumn`, `sortDirection`. Use a `filteredTasks` computed property that chains filter → sort. Display a count ("N tasks") and a search input + status dropdown above the table. Make column headers clickable for sort toggling.

### D9. Empty states: Icon + guidance text

- Kanban empty board: centered archive icon + "No tasks yet" + "Create your first task using the form above"
- Archived empty table: archive icon + "No archived tasks yet" + "Completed tasks are automatically archived after the configured retention period"
- Remove italic "No tasks" text from individual Kanban columns (empty column is self-evident)

### D10. Skeleton loading: animate-pulse placeholders

Replace "Loading tasks..." text in KanbanBoard with 6 skeleton column shapes. Replace "Loading archived tasks..." with 5 skeleton table rows. Replace "Loading settings..." with skeleton card shapes. All use Tailwind's `animate-pulse` on gray rounded rectangles.

### D11. Copy output button

Add a "Copy raw" button next to the Close button in TaskOutputModal. Uses `navigator.clipboard.writeText(props.output)`. Shows "Copied!" text for 2 seconds via a local `copied` ref with `setTimeout`.

### D12. Skill deletion confirmation

Add a confirmation dialog before deleting a skill in SkillsSettings.vue (or the equivalent section). Reuse the `<dialog>` pattern already established for task deletion in KanbanBoard.vue.

## File Structure

```
frontend/src/
  App.vue                              # Add <nav>, mount <Toaster>
  components/
    KanbanBoard.vue                    # Column width, empty states, skeleton loading
    TaskCard.vue                       # Category indicators, description preview, running state
    TaskEditModal.vue                  # Backdrop-click dismiss with dirty guard
    TaskOutputModal.vue                # Copy-to-clipboard button
  pages/
    SettingsPage.vue                   # Decompose into orchestrator
    ArchivedTasksPage.vue              # Search, filter, sort, empty/loading states
  components/settings/                 # NEW directory
    SystemPromptSettings.vue
    SkillsSettings.vue
    LlmModelSettings.vue
    TaskManagementSettings.vue
    McpApiKeySettings.vue
    GitSshKeySettings.vue
    McpServerConfigSettings.vue
```
