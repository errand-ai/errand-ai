## Context

The archived tasks page displays a table of archived/deleted tasks. Clicking a row opens the full `TaskEditModal` in read-only mode. The existing `TaskOutputModal` component (used on the kanban board) provides a lightweight popup for viewing task execution output. The archived tasks API already returns the `output` field on each task.

## Goals / Non-Goals

**Goals:**
- Add a "View Output" button to each archived task row that has output
- Reuse the existing `TaskOutputModal` component
- Prevent the button click from also triggering the row-click edit modal

**Non-Goals:**
- Changing the `TaskOutputModal` component itself
- Adding runner logs to the output modal (those are visible in the edit modal)
- Backend changes (the API already returns output)

## Decisions

### 1. Add an Actions column with a "View Output" button

**Decision**: Add a new column to the table with a button that opens `TaskOutputModal`. The button only renders for tasks where `output` is non-null and non-empty.

**Alternative**: Add an icon button inline with the title. Rejected — a dedicated column is clearer and consistent with table conventions.

### 2. Use `@click.stop` to prevent row-click propagation

**Decision**: Use Vue's `@click.stop` modifier on the button so clicking it does not also trigger the row's `@click` handler (which opens the edit modal).

## Risks / Trade-offs

- **[Minimal risk]** This is a small, additive frontend change with no backend impact. The only risk is layout — the extra column may slightly compress existing columns on narrow screens. → The Actions column will be narrow (icon-sized button), so impact is negligible.
