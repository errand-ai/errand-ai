## Context

The Kanban board currently has 6 columns: New, Scheduled, Pending, Running, Review, Completed. The "New" column exists for tasks that couldn't be fully processed — either the input was too short (5 words or fewer) or the LLM failed to classify it. These tasks get a "Needs Info" tag and remain in `new` status until the user edits them to add enough detail (triggering auto-promotion to `scheduled`).

The "Review" column already serves as a "needs human attention" area — it's where completed tasks land for user review. Moving "Needs Info" tasks there is a natural fit since both represent "user should look at this".

## Goals / Non-Goals

**Goals:**

- Remove the `new` column and status from the workflow entirely
- Route tasks that would have been `new` to `review` instead
- Migrate existing `new` tasks in the database to `review`
- Move "Review" to be the first (leftmost) column to reflect its new dual purpose
- Clean up all references to the `new` status across backend, frontend, and tests

**Non-Goals:**

- Renaming the "Review" column (it stays as "Review" — the name works for both use cases)
- Changing how the "Needs Info" tag works (it's still applied for short inputs and LLM failures)
- Changing the auto-routing for successfully processed tasks (immediate → pending, scheduled/repeating → scheduled)

## Decisions

### 1. Remove `new` from `VALID_STATUSES` entirely

**Decision**: Remove `new` from the status enum rather than keeping it as a hidden/deprecated status.

**Alternatives considered**:
- *Keep `new` in VALID_STATUSES but hide the column*: Would leave dead code paths and confuse future development.

**Rationale**: A clean removal is simpler. The migration handles existing data. Any external API consumers sending `status: "new"` will get a 422 validation error, which is the correct behaviour for a removed status.

### 2. Alembic migration for existing `new` tasks

**Decision**: Add a data migration that does `UPDATE tasks SET status = 'review' WHERE status = 'new'`.

**Rationale**: Simple, reversible (downgrade can set them back), and handles any existing data in production.

### 3. Auto-promotion logic removed

**Decision**: Remove the auto-promotion code path that detects `status == "new"` + "Needs Info" + description + scheduling fields on PATCH and promotes to `scheduled`. Since tasks can no longer be in `new` status, this code path is unreachable.

**Alternatives considered**:
- *Adapt to trigger from `review` status instead*: Over-complicated — if a user edits a review task to add scheduling, they can just drag it to Scheduled.

**Rationale**: The auto-promotion was a convenience for the New → Scheduled transition. With Review as a general-purpose "needs attention" column, manual drag-and-drop is sufficient.

### 4. Review column becomes reorderable

**Decision**: Change `REORDERABLE_COLUMNS` from `['new', 'pending']` to `['review', 'pending']`.

**Rationale**: Review is now the first column and replaces New's role. Users should be able to reorder tasks in it just as they could in the New column.

## Risks / Trade-offs

**[API breaking change for `status: "new"`]** → Accepted. The user has confirmed no backwards compatibility is needed. The 422 validation error for `new` is clear enough.

**["Needs Info" tasks mixed with completed-review tasks in the same column]** → The "Needs Info" tag visually distinguishes them. Both task types benefit from the same user action: look at this and decide what to do.

**[Existing data migration]** → Low risk. Simple `UPDATE ... SET status = 'review' WHERE status = 'new'` with no cascading effects.
