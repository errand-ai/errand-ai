## Why

The project has zero automated tests. The recent verification of `update-kanban-columns` identified 28 scenarios across 4 specs with no test coverage. Without tests, every deployment relies on manual verification, and regressions can ship undetected. Adding tests now — while the codebase is small — establishes the testing patterns that all future changes will follow.

## What Changes

- Add backend test infrastructure: pytest + httpx async test client with an in-memory SQLite database for isolation
- Add frontend test infrastructure: Vitest + Vue Test Utils for component-level testing
- Write backend API tests covering the `task-api` spec scenarios (CRUD, validation, status enforcement, auth gating)
- Write frontend component tests covering `task-edit-modal`, `task-drag-drop`, and `kanban-frontend` scenarios (rendering, interactions, store integration)
- Add `test` scripts to backend and frontend for local execution
- Add a CI test job that runs both backend and frontend tests before building images

## Capabilities

### New Capabilities
- `backend-tests`: pytest test suite for FastAPI backend covering task API endpoints, status validation, and auth gating
- `frontend-tests`: Vitest test suite for Vue components covering kanban board rendering, drag-and-drop interactions, and edit modal behavior

### Modified Capabilities
- `ci-pipelines`: Add a test job that runs backend and frontend tests, gating the build jobs

## Impact

- **Backend**: New `backend/tests/` directory with `conftest.py` (async fixtures, test DB, auth mocking) and test modules. New dev dependencies: `pytest`, `pytest-asyncio`, `httpx`.
- **Frontend**: New `frontend/src/__tests__/` or `frontend/tests/` directory with component test files. New dev dependencies: `vitest`, `@vue/test-utils`, `jsdom`.
- **CI**: `.github/workflows/build.yml` gains a `test` job that `build-frontend` and `build-backend` depend on.
- **Docker**: No changes — tests run outside containers using lightweight in-memory backends.
