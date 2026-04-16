## ADDED Requirements

### Requirement: Safe ORM task data handoff after session close
When the TaskManager dequeues a task for processing, it SHALL copy all required task fields into a plain Python object (dataclass or dict) while the database session is still open. The ORM instance SHALL NOT be passed to the spawned processing coroutine. This prevents `DetachedInstanceError` from attribute access after the source session is closed.

#### Scenario: Task fields accessible after session closes
- **WHEN** a task is dequeued and the database session is closed before the processing coroutine runs
- **THEN** the processing coroutine can access all task fields without raising `DetachedInstanceError`

#### Scenario: ORM instance not referenced after session close
- **WHEN** a task processing coroutine starts
- **THEN** it receives a plain data object (not a SQLAlchemy ORM instance bound to a closed session)

### Requirement: Cached sync database engine
The `_resolve_provider_sync` function SHALL use a module-level cached sync engine instead of calling `create_sync_engine()` on every invocation. The engine SHALL be created once (lazily on first call or at module import) and reused for all subsequent calls. The engine SHALL never be created more than once per process lifetime.

#### Scenario: Engine created once per process
- **WHEN** `_resolve_provider_sync` is called multiple times during the lifetime of the server process
- **THEN** `create_sync_engine()` is called exactly once and the same engine instance is reused

#### Scenario: Engine reused across concurrent calls
- **WHEN** multiple tasks call `_resolve_provider_sync` concurrently
- **THEN** all calls use the same cached engine and no new connection pools are created
