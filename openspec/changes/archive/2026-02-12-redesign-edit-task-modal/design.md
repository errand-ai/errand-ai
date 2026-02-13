## Context

The `TaskEditModal.vue` component currently renders all fields in a single column at a fixed width of `w-[28rem]` (448px). Every field — whether a single-line dropdown or a multi-line textarea — stretches to full width and stacks vertically. The description textarea is limited to 3 rows, and the recently-added runner logs are hidden behind a collapsed `<details>` toggle capped at 256px.

The project uses default Tailwind CSS breakpoints (`sm:640px`, `md:768px`, `lg:1024px`) with no custom overrides. The existing `TaskOutputModal` already demonstrates the pattern of `max-h-[80vh]` with `flex-col` for viewport-bounded modals.

The modal is opened from `KanbanBoard.vue` via the `editingTask` ref and receives a `TaskData` object as a prop. No script logic or data flow needs to change — this is purely a template/layout restructure.

## Goals / Non-Goals

**Goals:**
- Use available screen width on desktop to display more information with less scrolling
- Give description and runner logs more vertical space so their content is visible without extra interaction
- Group related metadata fields compactly so short fields don't waste vertical space
- Keep the modal usable on narrow viewports by falling back to single-column
- Bound the modal height to the viewport so it doesn't overflow off-screen

**Non-Goals:**
- Resizable or draggable modal (keep native `<dialog>` behaviour)
- Changing which fields are displayed or how data is saved (same form fields, same emit payload)
- Adding new fields or features (pure layout change)
- Mobile-first redesign (the app is primarily used on desktop; narrow-screen support is a graceful fallback, not a primary target)

## Decisions

### 1. Two-column grid layout with CSS Grid

**Decision**: Use a CSS Grid (`grid grid-cols-1 md:grid-cols-2 gap-6`) as the main layout container inside the form, with Title spanning both columns and action buttons below the grid.

**Rationale**: CSS Grid provides clean two-column layout with `col-span-2` for full-width elements. Tailwind's responsive prefix (`md:`) handles the breakpoint naturally. Flexbox would work but requires more wrapper divs for the same result.

**Alternative considered**: Flexbox with percentage widths — more verbose, harder to maintain column alignment.

### 2. Modal width: `max-w-3xl w-full mx-auto`

**Decision**: Set the modal form to `max-w-3xl` (768px) with `w-full`, replacing the fixed `w-[28rem]` (448px).

**Rationale**: 768px provides enough room for two comfortable columns (each ~360px minus gap) without feeling overly wide. It's the `md` breakpoint width, so below this the grid naturally collapses to single-column. Using `max-w-3xl` with `w-full` means the modal is responsive — it will shrink on narrow viewports rather than overflow.

**Alternatives considered**:
- `max-w-4xl` (896px) — tested but felt too wide for the amount of content; the metadata column would have excessive whitespace
- `max-w-2xl` (672px) — too tight for two comfortable columns with tags and datetime pickers

### 3. Column assignment

**Decision**:
- **Left column**: Status, Category, Execute at / Completed at, Repeat fields (conditional), Tags
- **Right column**: Description (expanded textarea), Runner Logs (always visible when present)
- **Full-width (span both columns)**: Title (top), Error message, Action buttons (bottom)

**Rationale**: Groups related metadata fields in the left column where they stack compactly (dropdowns and date pickers are short). Places the two potentially long-content fields in the right column where they can share a taller vertical space. Title stays full-width because it's the primary identifier. Action buttons stay full-width at the bottom for conventional form UX.

### 4. Description textarea: increase from 3 rows to 8 rows

**Decision**: Increase the description `rows` attribute from `3` to `8` to make better use of the right column height.

**Rationale**: With the metadata fields stacked in the left column, the right column has vertical space to fill. A taller description field displays more content without scrolling. 8 rows (~192px) roughly matches the height of the left column's stacked fields.

### 5. Runner logs: replace `<details>` with always-visible read-only panel

**Decision**: Remove the `<details>/<summary>` wrapper. When `task.runner_logs` is present, render it directly as a read-only `<pre>` block below the description in the right column, with a heading label. Keep `max-h-48` and `overflow-auto` for bounded scrolling.

**Rationale**: The collapsed toggle hides potentially important diagnostic information. With the wider modal and two-column layout, there's room to show logs by default. The `max-h-48` (192px) prevents logs from dominating the modal while still showing meaningful content. The runner logs panel only appears when logs exist (same `v-if` condition), so it doesn't waste space for tasks that haven't been run.

**Alternative considered**: Keep `<details>` but default to open — adds visual noise of the toggle arrow for no benefit when we have the space.

### 6. Viewport height bounding: `max-h-[85vh]` with overflow

**Decision**: Add `max-h-[85vh] overflow-y-auto` to the form container, matching the pattern used by `TaskOutputModal` (`max-h-[80vh]`). Use 85vh rather than 80vh because the edit modal has action buttons that should stay visible.

**Rationale**: The current modal has no height bound, so on smaller screens or with repeating category fields visible, it can extend beyond the viewport. The `TaskOutputModal` already solves this with `max-h-[80vh] flex flex-col`. The edit modal needs the same treatment.

### 7. Responsive breakpoint: `md` (768px)

**Decision**: Use Tailwind's `md:` prefix for the two-column grid. Below 768px, the grid collapses to a single stacked column (the current layout behaviour).

**Rationale**: The `md` breakpoint (768px) is the natural threshold — the `max-w-3xl` modal is 768px wide, so below this the modal already fills the viewport width and two columns would be too cramped. No custom breakpoints needed.

## Risks / Trade-offs

- **[Test updates required]** → Tests that assert runner logs are inside a `<details>/<summary>` element will break. Mitigation: update tests to query for the `<pre>` block directly instead of through `<details>`.
- **[Left column height mismatch]** → If a task has category "repeating" (showing repeat interval + repeat until fields), the left column becomes taller and may push past the right column. → Mitigation: both columns scroll independently within the `max-h-[85vh]` container; the grid handles uneven column heights gracefully.
- **[Narrow viewport scrolling]** → On viewports below 768px, the single-column fallback will be taller than the current modal (description now has 8 rows instead of 3). → Mitigation: the `max-h-[85vh] overflow-y-auto` ensures it stays within the viewport with scrolling.

## Open Questions

_(none — the design is straightforward with no external dependencies or migration concerns)_
