## 1. Backend

- [x] 1.1 Update the `GET /api/tasks` query in `backend/main.py` to sort completed tasks by `updated_at` descending instead of `position` ascending. Use a `case()` expression or split query approach so other columns retain their current `position ASC, created_at ASC` ordering.

## 2. Tests

- [x] 2.1 Add a backend test verifying that completed tasks are returned in `updated_at` descending order (most recently completed first)
- [x] 2.2 Add a backend test verifying that non-completed tasks (e.g. pending) still return in `position ASC, created_at ASC` order

## 3. Verification

- [x] 3.1 Rebuild with `docker compose up --build` and verify the completed column shows most recently completed tasks at the top
