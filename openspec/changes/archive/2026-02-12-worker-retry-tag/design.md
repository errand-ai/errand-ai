## Context

The worker's `_schedule_retry` function moves failed tasks back to "scheduled" status with exponential backoff. The existing "Input Needed" tag pattern (lines 446-458 in `worker.py`) shows how to find-or-create a tag and associate it with a task via the `task_tags` association table.

Currently `_schedule_retry` uses a bulk `UPDATE` statement and doesn't load the task's tags relationship, so adding a tag requires a small refactor to work with the ORM relationship or use the association table directly.

## Goals / Non-Goals

**Goals:**
- Add a "Retry" tag to tasks when `_schedule_retry` moves them back to scheduled
- Remove the "Retry" tag when a task completes successfully or moves to review
- Follow the existing tag pattern used for "Input Needed"

**Non-Goals:**
- Changing retry logic (backoff, max retries)
- Adding retry count display in the UI (already visible via `retry_count` field)
- Adding a max retry limit

## Decisions

### Decision: Add tag in `_schedule_retry`, remove in success path

Add the "Retry" tag inside `_schedule_retry` after the UPDATE statement, using the same session. Remove it in the success path (exit_code == 0, parsed successfully) before committing.

**Rationale:** Keeps the tag lifecycle tied to the retry flow. The tag appears when retry happens and disappears when the task succeeds — no stale tags.

### Decision: Use association table directly (not ORM relationship)

Insert into `task_tags` directly, same as the "Input Needed" pattern. This avoids needing to reload the full task ORM object with its tags relationship in `_schedule_retry`.

**Rationale:** Matches existing code pattern, minimal change.

## Risks / Trade-offs

- **[Duplicate tag association]** → Check for existing association before inserting, or use `INSERT ... ON CONFLICT DO NOTHING` pattern. Since SQLAlchemy's `task_tags.insert()` is used, guard with a select-before-insert like the existing pattern.
- **[Tag not removed if task bypasses success path]** → Only matters if a task is manually moved out of scheduled. Acceptable — the tag is informational and can be manually removed.
