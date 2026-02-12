## Why

The edit task modal uses a narrow single-column layout (`w-[28rem]` / 448px) where every field — from single-line dropdowns to multi-line text areas — occupies the full width. This wastes vertical space on short fields (Status, Category, Execute at) while constraining long-content fields (Description at 3 rows, Runner Logs capped at 256px in a collapsed `<details>` block). As tasks accumulate richer descriptions and runner logs, the modal requires excessive scrolling and hides important information behind a collapsed toggle. A multi-panel layout would make better use of available screen width on desktop while keeping the modal usable on smaller viewports.

## What Changes

- Widen the modal from `w-[28rem]` (448px) to a responsive width that uses more available viewport space on desktop (e.g. `max-w-4xl` / 896px), with a fallback to single-column on narrow screens
- Reorganise fields into a two-column layout:
  - **Left column**: Short metadata fields (Status, Category, Execute at / Completed at, Repeat interval, Repeat until, Tags) arranged compactly, possibly with Status and Category side-by-side on one row
  - **Right column**: Long-content fields (Description textarea with more rows, Runner Logs) given more vertical space
- Title remains full-width across both columns at the top
- Runner Logs promoted from a collapsed `<details>` block to a visible panel (read-only) in the right column, below Description, with taller max-height
- Action buttons (Delete, Cancel, Save) remain full-width at the bottom
- On narrow viewports (below ~640px), the layout falls back to a single stacked column

## Capabilities

### New Capabilities

_(none — this is a layout redesign of an existing component)_

### Modified Capabilities

- `task-edit-modal`: Layout changes from single-column to responsive two-column; Runner Logs display changes from collapsed `<details>` to always-visible read-only panel; modal width increases

## Impact

- **Frontend**: `TaskEditModal.vue` — template restructured with Tailwind grid/flex classes; no script logic changes
- **Tests**: `TaskEditModal.test.ts` — tests that query specific DOM structure may need updating (e.g. runner logs no longer inside `<details>/<summary>`)
- **No backend changes** — this is purely a frontend layout change
- **No API changes** — same fields, same save/delete behaviour
- **No new dependencies** — uses existing Tailwind utilities
