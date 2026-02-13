## Approach

Modify the backend `GET /api/tasks` query to apply different sort logic for completed tasks versus other columns. The frontend already renders tasks in API response order, so no frontend changes are needed.

## Decision: Sort in the backend query

The task list endpoint currently uses a single query with `ORDER BY position ASC, created_at ASC` for all non-archived/non-deleted tasks. Since the completed column needs `updated_at DESC` ordering while other columns need `position ASC`, we'll split the query into two parts and combine the results, or apply a conditional order.

**Chosen approach:** Use a SQL `CASE` expression in the `ORDER BY` clause to apply different sort keys per status. This keeps it as a single query and avoids changing the response structure.

Specifically:
- For status `completed`: order by `updated_at DESC`
- For all other statuses: order by `position ASC, created_at ASC` (unchanged)

Since SQLAlchemy returns all tasks in one flat list and the frontend groups them by status, the relative ordering within each status group is what matters — the cross-status ordering is irrelevant.

## Decision: No frontend changes

The KanbanBoard component groups tasks by `task.status` and renders them in the order they appear in the filtered array. As long as the API returns completed tasks in the correct order, the frontend displays them correctly without changes.

## Risks

- **None significant.** This is a small, isolated backend change to the sort clause of one query. No schema changes, no API contract changes, no frontend changes.
