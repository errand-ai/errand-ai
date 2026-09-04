## ADDED Requirements

### Requirement: Hindsight stores its tables in a schema of the errand database

The compose environments SHALL point Hindsight at the same PostgreSQL database errand uses, isolated by schema rather than by database. Hindsight SHALL receive `HINDSIGHT_API_DATABASE_SCHEMA=hindsight`, and the database initialisation script SHALL NOT create a separate `hindsight` database. Alembic SHALL continue to own the `public` schema and SHALL NOT create, read or migrate anything in the `hindsight` schema.

#### Scenario: Single database in compose

- **WHEN** the compose environment is brought up
- **THEN** Hindsight's connection string names the same database as errand's `DATABASE_URL`
- **AND** `HINDSIGHT_API_DATABASE_SCHEMA` is `hindsight`

#### Scenario: Init script no longer creates a hindsight database

- **WHEN** `deploy/init-databases.sh` runs
- **THEN** it creates the `litellm` database only
- **AND** it does not issue `CREATE DATABASE hindsight`

#### Scenario: pgvector available in the shared database

- **WHEN** the compose PostgreSQL image starts
- **THEN** the `vector` extension is available and installed in the errand database before Hindsight first connects

### Requirement: Hindsight Control Plane is opt-in and off by default

The Control Plane SHALL be defined as a separate compose service behind a profile, and SHALL NOT start or publish a port during a default `docker compose up`. Starting it SHALL require explicitly selecting that profile.

#### Scenario: Default bring-up omits the Control Plane

- **WHEN** the compose environment is started without profile selection
- **THEN** no Control Plane container is created
- **AND** no host port is published for it

#### Scenario: Control Plane started on request

- **WHEN** the compose environment is started with the memory-UI profile selected
- **THEN** the Control Plane container starts and is reachable
- **AND** it is configured with the API service URL and, when the API requires one, the matching bearer

### Requirement: Hindsight volume ownership is prepared before first start

Every compose file that mounts a host-managed volume into the Hindsight container SHALL ensure the mounted paths are owned by the container's non-root user before the service starts. This applies to the model/cache directory as well as any embedded-database directory.

#### Scenario: Cache volume chowned in the deployment compose file

- **WHEN** `deploy/docker-compose.yml` is brought up for the first time with empty volumes
- **THEN** an initialisation step makes the mounted cache directory writable by the container user
- **AND** Hindsight starts without `PermissionError` on its Hugging Face cache directory

#### Scenario: Both mounted directories are covered

- **WHEN** a compose file mounts both a data directory and a cache directory into Hindsight
- **THEN** the initialisation step covers both paths, not only the data directory
