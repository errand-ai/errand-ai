## Context

The edit task modal (`TaskEditModal.vue`) uses a CSS Grid with `grid-cols-1 md:grid-cols-2` — an equal 50:50 split at `md` and above. The left column holds metadata (status, category, dates, tags) and the right column holds content (description textarea, runner logs). The runner logs are constrained to the right column width, but log lines are often wide, making them hard to read.

## Goals / Non-Goals

**Goals:**
- Adjust the two-column ratio to ~35:65 so the narrower metadata column doesn't waste horizontal space
- Move runner logs to a full-width row at the bottom so long log lines are more readable
- Expand the description textarea to fill the right column height, making better use of vertical space

**Non-Goals:**
- Changing modal max-width or viewport height constraints
- Changing the single-column (mobile) layout behaviour
- Changing any field behaviour, validation, or API interactions
- Restyling fields, colours, or typography

## Decisions

### 1. Column ratio via custom grid template

**Decision**: Use `md:grid-cols-[1fr_2fr]` instead of `md:grid-cols-2`.

This gives roughly 33:67 which is close to the 35:65 target. Using fractional units keeps the layout fluid and avoids fixed pixel widths. An alternative like `grid-cols-[35%_65%]` would also work but percentage-based columns don't account for gaps the same way `fr` units do.

### 2. Runner logs as a full-width bottom row

**Decision**: Move the runner logs `<div>` out of the right column and into a full-width `md:col-span-2` row, positioned between the two-column content and the action buttons row.

This is a straightforward template reorder — the runner logs block moves from inside the right-column `<div>` to a sibling of the column containers, with `md:col-span-2` to span both columns.

### 3. Description textarea fills right column height

**Decision**: Convert the right column from `space-y-4` to a flex column (`flex flex-col gap-4`) and set the description container to `flex-1` with the textarea using `h-full min-h-[8rem]` (preserving the current ~8-row minimum).

With runner logs removed from the right column, description is the only content field. Using flex-grow lets it stretch to match the left column height without a fixed row count. The `min-h-[8rem]` ensures a reasonable minimum even when the left column is short.

## Risks / Trade-offs

- **[Visual shift]** The 35:65 ratio is a subtle change; users accustomed to the equal split may notice the asymmetry. → Acceptable trade-off for better space utilisation.
- **[Textarea height variability]** The flex-grow description will be taller when there are more metadata fields visible (e.g. repeating tasks show extra fields). → This is actually desirable — more left-column fields means more right-column space for description.
- **[Test updates]** Tests that assert on grid classes or runner logs position will need updating. → Straightforward class/selector changes.
