## 1. Backend Test Infrastructure

- [x] 1.1 Create `backend/requirements-test.txt` with `pytest`, `pytest-asyncio`, `httpx`, `aiosqlite`
- [x] 1.2 Create `backend/tests/conftest.py` with async test client fixture: in-memory SQLite engine, create tables, override `get_session` and `get_current_user` dependencies, yield `httpx.AsyncClient` with `ASGITransport`
- [x] 1.3 Configure pytest in `backend/pyproject.toml` or `backend/pytest.ini` with `asyncio_mode = auto`

## 2. Backend API Tests

- [x] 2.1 Create `backend/tests/test_tasks.py` — test `GET /api/tasks` (retrieve tasks ordered by creation desc, empty list)
- [x] 2.2 Add tests for `POST /api/tasks` (successful creation with status `new`, missing/empty title → 422)
- [x] 2.3 Add tests for `GET /api/tasks/{id}` (task found → 200, not found → 404)
- [x] 2.4 Add tests for `PATCH /api/tasks/{id}` (update status, update title, update both, not found → 404, invalid status → 422, empty title → 422)
- [x] 2.5 Add tests for valid status enforcement (all 7 statuses accepted, invalid status `"failed"` → 422)
- [x] 2.6 Create `backend/tests/test_metrics.py` — test `GET /metrics/queue` (tasks pending count, zero pending, no auth required)
- [x] 2.7 Create `backend/tests/test_health.py` — test `GET /api/health` returns `{"status": "ok"}`
- [x] 2.8 Create `backend/tests/test_auth.py` — test unauthenticated request to `/api/tasks` returns 401/403

## 3. Frontend Test Infrastructure

- [x] 3.1 Add `vitest`, `@vue/test-utils`, `jsdom` to `frontend/package.json` devDependencies
- [x] 3.2 Add Vitest config in `frontend/vitest.config.ts` (or extend `vite.config.ts`) with jsdom environment
- [x] 3.3 Add `"test": "vitest run"` script to `frontend/package.json`
- [x] 3.4 Create `frontend/src/components/__tests__/` directory and test setup file (stub `HTMLDialogElement.prototype.showModal` / `close` if needed)

## 4. Frontend Component Tests

- [x] 4.1 Create `TaskCard.test.ts` — test card renders title, edit button, has `draggable="true"`, edit button emits `edit` event
- [x] 4.2 Create `TaskForm.test.ts` — test successful submission calls store `addTask`, empty title shows validation error without calling store
- [x] 4.3 Create `TaskEditModal.test.ts` — test modal shows current task data, status select has 7 options, save emits event with data, empty title validation, cancel emits event
- [x] 4.4 Create `KanbanBoard.test.ts` — test 7 columns render with correct labels, tasks placed in correct columns, empty state shows "No tasks", drag-drop handlers trigger store update, same-column drop does nothing, drag enter highlights column

## 5. CI Integration

- [x] 5.1 Add `test` job to `.github/workflows/build.yml` that installs Python + Node, runs `pytest` and `npm test`
- [x] 5.2 Update `build-frontend` and `build-backend` `needs` to include `test` job
- [x] 5.3 Verify all tests pass locally before committing
