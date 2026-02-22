## ADDED Requirements

### Requirement: Backend serves frontend static assets
The FastAPI application SHALL serve the frontend's built static assets from a `static/` directory when that directory exists. Vite-generated assets in `static/assets/` SHALL be served at the `/assets/` URL path. The static file mount SHALL only be registered if the `static/` directory is present at startup.

#### Scenario: Hashed asset served
- **WHEN** a browser requests `/assets/index-abc123.js`
- **THEN** the backend serves the file from `static/assets/index-abc123.js` with the correct `Content-Type` header

#### Scenario: Static directory missing
- **WHEN** the backend starts and no `static/` directory exists (e.g., during development)
- **THEN** no static file routes are registered and the backend operates as API-only

### Requirement: SPA fallback route
The FastAPI application SHALL include a catch-all route that serves `static/index.html` for any GET request whose path does not match an API route (`/api/`, `/auth/`, `/mcp/`, `/slack/`, `/metrics/`) and does not match a file in the `static/` directory. This route SHALL only be registered if the `static/` directory exists.

#### Scenario: SPA deep link
- **WHEN** a browser requests `/tasks/123` and no API route matches
- **THEN** the backend serves `static/index.html` so Vue Router handles the route client-side

#### Scenario: Root path
- **WHEN** a browser requests `/`
- **THEN** the backend serves `static/index.html`

#### Scenario: API routes unaffected
- **WHEN** a browser requests `/api/tasks`
- **THEN** the request is handled by the API route, not the SPA fallback

### Requirement: Static root files served at correct paths
Files in the root of the `static/` directory (e.g., `favicon.ico`, `robots.txt`) SHALL be served at their expected URL paths (e.g., `/favicon.ico`).

#### Scenario: Favicon served
- **WHEN** a browser requests `/favicon.ico` and `static/favicon.ico` exists
- **THEN** the backend serves the file with the correct content type

#### Scenario: Missing root file falls back to SPA
- **WHEN** a browser requests `/nonexistent.txt` and no such file exists in `static/`
- **THEN** the backend serves `static/index.html` (SPA fallback)

### Requirement: Combined Docker image
The application SHALL be built as a single Docker image using a multi-stage Dockerfile. The first stage SHALL use Node.js to build the frontend (`npm ci && npm run build`). The final stage SHALL use Python and copy the frontend build output into a `static/` directory alongside the application code. The build context SHALL be the repository root. The Dockerfile SHALL copy application source from `errand/` and requirements from `errand/requirements.txt`.

#### Scenario: Image contains frontend assets
- **WHEN** the Docker image is built
- **THEN** the final image contains `static/index.html` and `static/assets/` with the Vite build output

#### Scenario: Image does not contain Node.js
- **WHEN** the Docker image is built
- **THEN** the final image does not include Node.js, npm, or frontend source files

#### Scenario: Build context is repo root
- **WHEN** the Docker image is built
- **THEN** both `frontend/` and `errand/` directories are accessible in the build context
