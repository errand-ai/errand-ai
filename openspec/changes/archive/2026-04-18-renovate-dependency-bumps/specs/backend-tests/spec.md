## MODIFIED Requirements

### Requirement: Backend test infrastructure
The application SHALL have a pytest 9.x test suite using `pytest-asyncio` 1.x and `httpx.AsyncClient`. Tests SHALL run against an in-memory SQLite database via `aiosqlite`, with FastAPI dependency overrides for database sessions and authentication. The test database SHALL be created fresh for each test function.

#### Scenario: Test suite runs without external services
- **WHEN** a developer runs `pytest` in the errand directory
- **THEN** all tests execute without requiring PostgreSQL, Keycloak, or any external service

#### Scenario: Test isolation
- **WHEN** multiple test functions run sequentially
- **THEN** each test starts with an empty database and no shared state from previous tests

#### Scenario: pytest-asyncio mode
- **WHEN** the test suite is run with pytest-asyncio 1.x
- **THEN** async test functions SHALL be discovered and executed correctly, with asyncio_mode configured if required by the pytest-asyncio version
