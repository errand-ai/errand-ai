## MODIFIED Requirements

### Requirement: SPA fallback route
The FastAPI application SHALL serve `static/index.html` as the SPA fallback for any GET or HEAD request whose path does not match an API route (`/api/`, `/auth/`, `/mcp/`, `/slack/`, `/metrics/`) and does not correspond to a file under the `static/` directory, with the sole exception of paths beginning with `/assets/` which SHALL NOT use the SPA fallback. The fallback SHALL be implemented by delegating path resolution to `fastapi.staticfiles.StaticFiles` (via a subclass that serves `index.html` on a 404 from the base class) rather than by hand-rolled path handling. The SPA mount SHALL only be registered if the `static/` directory exists at startup and SHALL be registered after all API and auth routes so those routes continue to match first.

#### Scenario: SPA deep link
- **WHEN** a browser issues `GET /tasks/123` and no API route matches
- **THEN** the backend serves `static/index.html` with `Content-Type: text/html` so Vue Router handles the route client-side

#### Scenario: SPA deep link via HEAD
- **WHEN** a client issues `HEAD /tasks/123` and no API route matches
- **THEN** the backend returns `200` with `Content-Type: text/html` and no body

#### Scenario: Root path
- **WHEN** a browser requests `GET /`
- **THEN** the backend serves `static/index.html`

#### Scenario: Trailing slash on deep link
- **WHEN** a browser requests `GET /tasks/abc/`
- **THEN** the backend serves `static/index.html` (not a 404)

#### Scenario: API routes unaffected
- **WHEN** a browser requests `GET /api/tasks` or `GET /api/health`
- **THEN** the request is handled by the API route, never by the SPA fallback

#### Scenario: Auth routes unaffected
- **WHEN** a browser requests `GET /auth/login` or any `/auth/*` path
- **THEN** the request is handled by the auth route, never by the SPA fallback

#### Scenario: Path resolution delegated to library
- **WHEN** the SPA fallback resolves a request path to a filesystem location
- **THEN** the resolution SHALL be performed by `StaticFiles` (or a subclass thereof), not by application code that constructs filesystem paths from the request path

### Requirement: Missing asset requests fail loudly
Requests under the `/assets/` prefix that do not correspond to a file in `static/assets/` SHALL return HTTP `404`, not the SPA fallback. This ensures the browser surfaces missing bundle errors immediately rather than silently receiving HTML when JavaScript or CSS was expected.

#### Scenario: Missing hashed asset
- **WHEN** a browser requests `GET /assets/index-deadbeef.js` and no such file exists
- **THEN** the backend returns `404`, not `static/index.html`

#### Scenario: Missing asset of any type
- **WHEN** a browser requests `GET /assets/missing.css` and no such file exists
- **THEN** the backend returns `404`

### Requirement: Static root files served at correct paths
Files in the root of the `static/` directory (e.g., `favicon.ico`, `robots.txt`) SHALL be served at their expected URL paths with the correct `Content-Type` header. Requests for paths that do not match a root-level file AND do not match a mounted sub-path (e.g., `/assets/...`) SHALL fall back to `static/index.html` (SPA fallback).

#### Scenario: Favicon served
- **WHEN** a browser requests `GET /favicon.ico` and `static/favicon.ico` exists
- **THEN** the backend serves the file with `Content-Type: image/x-icon` (or `image/vnd.microsoft.icon`)

#### Scenario: Robots.txt served
- **WHEN** a browser requests `GET /robots.txt` and `static/robots.txt` exists
- **THEN** the backend serves the file with `Content-Type: text/plain`

#### Scenario: Missing root file falls back to SPA
- **WHEN** a browser requests `GET /nonexistent.html` (or any non-asset path with no matching file)
- **THEN** the backend serves `static/index.html` (SPA fallback)

### Requirement: Path-traversal attempts do not leak files outside static/
Any request path that attempts to escape the static directory (e.g., via `..` components or URL-encoded equivalents) SHALL either be normalised out by the ASGI stack or result in an SPA fallback / 404 from the static file server; the response SHALL NEVER contain the contents of a file outside `static/`.

#### Scenario: Literal traversal in path
- **WHEN** a client requests `GET /../../etc/passwd`
- **THEN** the response SHALL NOT contain the contents of `/etc/passwd`; it SHALL be either the SPA fallback, a 404, or a client-side normalised request

#### Scenario: URL-encoded traversal
- **WHEN** a client requests `GET /%2e%2e/%2e%2e/etc/passwd`
- **THEN** the response SHALL NOT contain the contents of `/etc/passwd`

#### Scenario: Double-slash traversal
- **WHEN** a client requests `GET //etc/passwd`
- **THEN** the response SHALL NOT contain the contents of `/etc/passwd`

#### Scenario: Hidden file in repo root
- **WHEN** a client requests `GET /.env` or `GET /.git/config` and no such file exists inside `static/`
- **THEN** the response SHALL be the SPA fallback (`index.html`) or a 404; it SHALL NEVER contain the contents of any file outside the `static/` directory
