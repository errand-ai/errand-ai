## MODIFIED Requirements

### Requirement: Docker Compose runs the full application stack
A `docker-compose.yml` at the repository root SHALL define services for PostgreSQL, database migration, errand (main application), worker, and Hindsight. Running `docker compose up` SHALL start the entire application locally. The errand service SHALL serve both API routes and frontend static files on port 8000. The errand and worker services SHALL receive `OPENAI_BASE_URL` and `OPENAI_API_KEY` environment variables. The errand service SHALL receive `ADMIN_USERNAME` and `ADMIN_PASSWORD` environment variables to auto-provision a local admin user on startup, allowing docker-compose users to skip the setup wizard and authenticate with known credentials.

#### Scenario: Full stack starts with local admin auto-provisioned
- **WHEN** a developer runs `docker compose up` with `ADMIN_USERNAME=admin` and `ADMIN_PASSWORD=changeme`
- **THEN** all services start, a local admin user is auto-created, and the developer can log in at `localhost:8000` with those credentials without going through the setup wizard

#### Scenario: Services start in correct order
- **WHEN** Docker Compose starts
- **THEN** PostgreSQL starts first, migrations run after PostgreSQL is healthy, and errand/worker start after migrations complete
