## ADDED Requirements

### Requirement: Display current user identity
The frontend SHALL display the authenticated user's name or email in the app header, derived from the access token claims.

#### Scenario: User identity shown
- **WHEN** a user is authenticated
- **THEN** the app header displays the user's name or email from the token

### Requirement: Logout button in header
The frontend SHALL display a logout button in the app header that triggers the logout action (redirect to `/auth/logout`).

#### Scenario: User clicks logout
- **WHEN** the user clicks the logout button
- **THEN** the browser navigates to `/auth/logout`

### Requirement: App is inaccessible without authentication
The Kanban board SHALL NOT render until the user is authenticated. Unauthenticated users SHALL be redirected to `/auth/login`.

#### Scenario: Unauthenticated user
- **WHEN** an unauthenticated user navigates to the app root
- **THEN** they are redirected to `/auth/login` before seeing any task data

## MODIFIED Requirements

### Requirement: Frontend is served as static assets
The frontend SHALL be built as static files and served by an nginx container. The nginx configuration SHALL proxy `/api/*` and `/auth/*` requests to the backend service.

#### Scenario: Static assets served
- **WHEN** a browser requests the application root
- **THEN** nginx serves the built Vue application

#### Scenario: API requests proxied
- **WHEN** the frontend makes a request to `/api/tasks`
- **THEN** nginx proxies the request to the backend service

#### Scenario: Auth requests proxied
- **WHEN** the browser requests `/auth/login`
- **THEN** nginx proxies the request to the backend service
