## Why

The edit task modal's two-column layout currently uses an equal 50:50 split, but the metadata fields (left) need less horizontal space than the content fields (right). The runner logs panel is placed in the right column below the description, but log lines are typically wide and benefit from the full modal width. Adjusting the proportions and repositioning the logs will make better use of the available space and improve readability.

## What Changes

- Change the two-column grid ratio from equal (`grid-cols-2`) to approximately 35:65 (e.g. `grid-cols-[1fr_2fr]`) at the `md` breakpoint and above
- Move the runner logs section from the right column to a full-width row spanning both columns at the bottom (above the action buttons)
- Expand the description textarea to fill the full remaining height of the right column (using flex layout or `flex-grow`) now that runner logs are no longer below it

## Capabilities

### New Capabilities

_(none)_

### Modified Capabilities

- `task-edit-modal`: Grid column ratio changes from equal split to ~35:65; runner logs moves to full-width bottom row; description textarea stretches to fill the right column height

## Impact

- **Frontend only**: `TaskEditModal.vue` template and Tailwind classes
- **Tests**: Layout-related assertions in `TaskEditModal.test.ts` may need updating (column ratio, runner logs placement)
- **Spec**: `task-edit-modal/spec.md` requirements for grid layout and runner logs position need updating
