## MODIFIED Requirements

### Requirement: Backend test script
The application SHALL have a test script runnable via `pytest` from the `errand/` directory. Dev dependencies (`pytest`, `pytest-asyncio`, `httpx`, `aiosqlite`) SHALL be listed in a separate requirements file.

#### Scenario: Run application tests
- **WHEN** a developer runs `pip install -r requirements-test.txt && pytest` in the `errand/` directory
- **THEN** all application tests execute and report results
