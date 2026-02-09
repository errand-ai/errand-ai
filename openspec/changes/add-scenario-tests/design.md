## Context

The content-manager project has zero automated tests. The backend is a FastAPI app with async SQLAlchemy (asyncpg/PostgreSQL), OIDC auth via Keycloak, and 7 API endpoints. The frontend is a Vue 3 + Pinia app with 4 components (KanbanBoard, TaskCard, TaskForm, TaskEditModal) and 1 composable (useApi). CI currently builds Docker images and a Helm chart but runs no tests.

The 4 testable specs (`task-api`, `kanban-frontend`, `task-edit-modal`, `task-drag-drop`) define 28 scenarios total. This change establishes test infrastructure and writes tests covering these scenarios.

## Goals / Non-Goals

**Goals:**
- Backend test suite that validates all `task-api` spec scenarios against the real FastAPI app (not mocked handlers)
- Frontend test suite that validates component rendering, interactions, and store behavior for `kanban-frontend`, `task-edit-modal`, and `task-drag-drop` scenarios
- CI gate: tests must pass before images are built
- Patterns that are easy to extend as new specs are added

**Non-Goals:**
- E2E/browser tests (Playwright) — deferred to a future change
- Testing auth routes (`/auth/login`, `/auth/callback`, `/auth/logout`) — these involve Keycloak redirects and are better suited for E2E tests
- Testing the Alembic migration scenario (requires a real PostgreSQL migration run)
- Testing the nginx proxy scenarios (`kanban-frontend` static/proxy specs) — infrastructure-level, not unit-testable
- Testing the "multiple replicas" statelessness scenario — deployment-level concern
- Load testing or performance benchmarks

## Decisions

### 1. Backend: pytest-asyncio + httpx AsyncClient with SQLite

**Choice:** Use `httpx.AsyncClient` with FastAPI's `ASGITransport` to send real HTTP requests to the app in-process, backed by an in-memory SQLite database via `aiosqlite`.

**Alternatives considered:**
- **TestClient (sync):** FastAPI's sync `TestClient` wraps requests but doesn't support async endpoints natively. Since all endpoints use `async def` and async SQLAlchemy, an async test client is the natural fit.
- **PostgreSQL testcontainer:** Provides full database fidelity but adds Docker dependency to CI, slows tests significantly, and is unnecessary since the app uses standard SQLAlchemy (no PostgreSQL-specific SQL). The one exception is `UUID(as_uuid=True)` — SQLite will store UUIDs as strings, which is acceptable for testing behavior.
- **Mocking SQLAlchemy:** Testing with mocked DB sessions doesn't validate the actual query logic. Real queries against SQLite give high confidence with minimal setup.

**Rationale:** In-memory SQLite is fast, requires no external services, and validates real SQL execution paths. The `UUID` column type works with SQLite when stored as string — SQLAlchemy handles the conversion. We override `get_session` dependency to inject the test database and `get_current_user` to bypass OIDC auth.

### 2. Backend: Auth bypass via dependency override

**Choice:** Override FastAPI's `get_current_user` dependency to return a fake claims dict, avoiding any OIDC/JWT setup in tests.

**Rationale:** The auth scenarios in `task-api` spec test two things: (a) authenticated requests succeed, and (b) unauthenticated requests get 401. For (a), the override provides a valid user. For (b), we remove the override and verify the raw app rejects the request. This avoids coupling tests to Keycloak configuration or JWT signing.

### 3. Backend: Skip lifespan OIDC discovery in tests

**Choice:** Create the test app without triggering the lifespan's `OIDCConfig.from_env()` / `oidc.discover()` call. Use a `@pytest.fixture` that creates a fresh `AsyncClient` per test with dependency overrides and a clean database.

**Rationale:** The lifespan requires `OIDC_DISCOVERY_URL`, `OIDC_CLIENT_ID`, and `OIDC_CLIENT_SECRET` env vars and makes a real HTTP call to Keycloak. Tests should run without any external services.

### 4. Frontend: Vitest + Vue Test Utils + jsdom

**Choice:** Use Vitest as the test runner (it shares Vite's config and module resolution), `@vue/test-utils` for mounting components, and `jsdom` as the DOM environment.

**Alternatives considered:**
- **Jest:** Requires separate configuration for Vue SFC, TypeScript, and ES modules. Vitest understands the existing `vite.config.ts` natively.
- **happy-dom:** Lighter than jsdom but less complete. jsdom has better `<dialog>` element support, which `TaskEditModal` uses.

**Rationale:** Vitest integrates directly with the existing Vite build setup and handles `.vue` SFCs, TypeScript, and Tailwind imports without additional configuration.

### 5. Frontend: Mock fetch, not the store

**Choice:** Mock the global `fetch` function (or the `useApi` composable) rather than mocking the Pinia store. Mount real components with a real Pinia store that calls mocked API functions.

**Rationale:** Mocking at the fetch/API layer tests the full component → store → API integration path. Mocking the store would skip testing how components react to store state changes, which is where most bugs occur.

### 6. CI: Add a `test` job that gates builds

**Choice:** Add a single `test` job that runs both backend and frontend tests. The existing `build-frontend` and `build-backend` jobs will depend on `test` in addition to `version`.

**Rationale:** Tests are fast (seconds) and should block image builds. A single job avoids the overhead of two separate CI runners for tests that each take under 30 seconds. Both test suites use lightweight tooling (pip + npm) without Docker.

## Risks / Trade-offs

- **SQLite vs PostgreSQL fidelity** — SQLite handles UUID as string and lacks PostgreSQL-specific features (e.g., `text("'new'")` server_default works differently). Mitigation: the app uses standard SQLAlchemy; no raw PostgreSQL SQL is used. If a PostgreSQL-specific issue arises in the future, we can add targeted integration tests.
- **`<dialog>` element in jsdom** — jsdom's `<dialog>` implementation may not fully support `showModal()` / `close()`. Mitigation: stub `HTMLDialogElement.prototype.showModal` and `close` in test setup if needed.
- **Drag-and-drop in jsdom** — HTML5 DnD events (`dragstart`, `dragover`, `drop`) can be simulated but don't behave identically to a real browser. Mitigation: test the event handlers and state changes, not the visual drag behavior (that's for E2E tests).
- **CI runtime** — Adding Python + Node setup to CI adds ~60s of setup time. Mitigation: use `actions/setup-python` and `actions/setup-node` with caching to minimize install time.
