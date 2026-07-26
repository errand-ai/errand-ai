from collections.abc import AsyncGenerator

import pytest
from fakeredis.aioredis import FakeRedis
from httpx import ASGITransport, AsyncClient
from sqlalchemy import event, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

import events as events_module
from models import Base, PlatformCredential, Task
from main import app, get_current_user, require_editor, require_admin
from database import get_session
from task_generator_routes import _require_admin as _tg_require_admin
from webhook_trigger_routes import _require_admin as _wt_require_admin
from jira_credential_routes import _require_admin as _jc_require_admin
from plugin_routes import _require_admin as _pl_require_admin

FAKE_USER_CLAIMS = {
    "sub": "test-user-id",
    "preferred_username": "testuser",
    "email": "test@example.com",
    "resource_access": {
        "errand": {
            "roles": ["user", "editor"],
        }
    },
    "_roles": ["user", "editor"],
}

FAKE_ADMIN_CLAIMS = {
    "sub": "admin-user-id",
    "preferred_username": "adminuser",
    "email": "admin@example.com",
    "resource_access": {
        "errand": {
            "roles": ["user", "admin"],
        }
    },
    "_roles": ["user", "admin"],
}

FAKE_VIEWER_CLAIMS = {
    "sub": "viewer-user-id",
    "preferred_username": "vieweruser",
    "email": "viewer@example.com",
    "resource_access": {
        "errand": {
            "roles": ["viewer"],
        }
    },
    "_roles": ["viewer"],
}

# SQLite-compatible DDL (replaces now() with CURRENT_TIMESTAMP, JSONB with TEXT)
_TASKS_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS tasks (
    id VARCHAR(36) NOT NULL PRIMARY KEY,
    title TEXT NOT NULL,
    description TEXT,
    status TEXT DEFAULT 'review' NOT NULL,
    category TEXT DEFAULT 'immediate',
    execute_at DATETIME,
    repeat_interval TEXT,
    repeat_until DATETIME,
    position INTEGER DEFAULT 0 NOT NULL,
    output TEXT,
    runner_logs TEXT,
    questions TEXT,
    retry_count INTEGER DEFAULT 0 NOT NULL,
    heartbeat_at DATETIME,
    profile_id VARCHAR(36) REFERENCES task_profiles(id) ON DELETE SET NULL,
    created_by TEXT,
    updated_by TEXT,
        encrypted_env TEXT,
    is_eval BOOLEAN DEFAULT 0 NOT NULL,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL
)
"""

_EVAL_RUNS_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS eval_runs (
    id VARCHAR(36) NOT NULL PRIMARY KEY,
    mode TEXT NOT NULL,
    started_at DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL,
    finished_at DATETIME,
    corpus_version TEXT NOT NULL,
    errand_version TEXT NOT NULL,
    judge_model TEXT NOT NULL,
    driver_host TEXT,
    notes TEXT
)
"""

_EVAL_RESULTS_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS eval_results (
    id VARCHAR(36) NOT NULL PRIMARY KEY,
    run_id VARCHAR(36) NOT NULL REFERENCES eval_runs(id) ON DELETE CASCADE,
    workload TEXT NOT NULL,
    model TEXT NOT NULL,
    task_id VARCHAR(36) REFERENCES tasks(id) ON DELETE SET NULL,
    rep INTEGER NOT NULL,
    verdict TEXT NOT NULL,
    score NUMERIC,
    turns INTEGER,
    recoveries INTEGER,
    error_events INTEGER,
    wall_seconds NUMERIC,
    judge_output TEXT,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL,
    UNIQUE (run_id, workload, model, rep)
)
"""

_SETTINGS_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS settings (
    key TEXT NOT NULL PRIMARY KEY,
    value TEXT NOT NULL,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL
)
"""

_TAGS_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS tags (
    id VARCHAR(36) NOT NULL PRIMARY KEY,
    name TEXT NOT NULL UNIQUE
)
"""

_TASK_TAGS_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS task_tags (
    task_id VARCHAR(36) NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
    tag_id VARCHAR(36) NOT NULL REFERENCES tags(id) ON DELETE CASCADE,
    PRIMARY KEY (task_id, tag_id)
)
"""

_PLATFORM_CREDENTIALS_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS platform_credentials (
    platform_id TEXT NOT NULL PRIMARY KEY,
    encrypted_data TEXT NOT NULL,
    status TEXT DEFAULT 'disconnected' NOT NULL,
    last_verified_at DATETIME,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL
)
"""

_SKILLS_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS skills (
    id VARCHAR(36) NOT NULL PRIMARY KEY,
    name TEXT NOT NULL UNIQUE,
    description TEXT NOT NULL,
    instructions TEXT NOT NULL,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL
)
"""

_SKILL_FILES_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS skill_files (
    id VARCHAR(36) NOT NULL PRIMARY KEY,
    skill_id VARCHAR(36) NOT NULL REFERENCES skills(id) ON DELETE CASCADE,
    path TEXT NOT NULL,
    content TEXT NOT NULL,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL,
    UNIQUE(skill_id, path)
)
"""

_TASK_PROFILES_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS task_profiles (
    id VARCHAR(36) NOT NULL PRIMARY KEY,
    name TEXT NOT NULL UNIQUE,
    description TEXT,
    match_rules TEXT,
    model TEXT,
    system_prompt TEXT,
    max_turns INTEGER,
    reasoning_effort TEXT,
    llm_timeout INTEGER,
    mcp_servers TEXT,
    litellm_mcp_servers TEXT,
    skill_ids TEXT,
            include_git_skills BOOLEAN NOT NULL DEFAULT 1,
    enabled_plugins TEXT,
    shared_workspace_enabled BOOLEAN NOT NULL DEFAULT 0,
    shared_workspace_subpath TEXT,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL
)
"""

_MARKETPLACES_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS marketplaces (
    id VARCHAR(36) NOT NULL PRIMARY KEY,
    name TEXT NOT NULL UNIQUE,
    source_type TEXT NOT NULL,
    source_url TEXT NOT NULL,
    ref TEXT,
    auth_token_encrypted TEXT,
    enabled BOOLEAN NOT NULL DEFAULT 1,
    predefined BOOLEAN NOT NULL DEFAULT 0,
    cached_manifest TEXT,
    last_synced_at DATETIME,
    last_sync_status TEXT,
    last_sync_error TEXT,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL
)
"""

_PLUGINS_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS plugins (
    id VARCHAR(36) NOT NULL PRIMARY KEY,
    marketplace_id VARCHAR(36) REFERENCES marketplaces(id) ON DELETE SET NULL,
    plugin_name TEXT NOT NULL,
    source_type TEXT,
    source_url TEXT,
    ref TEXT,
    auth_token_encrypted TEXT,
    installed_version TEXT NOT NULL,
    latest_available_version TEXT,
    enabled BOOLEAN NOT NULL DEFAULT 0,
    manifest TEXT,
    ignored_artifacts TEXT,
    skill_conflicts TEXT,
    installed_at DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL,
    last_checked_at DATETIME,
    UNIQUE(marketplace_id, plugin_name)
)
"""

_LOCAL_USERS_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS local_users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    role TEXT DEFAULT 'admin' NOT NULL,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL
)
"""

_TASK_GENERATORS_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS task_generators (
    id VARCHAR(36) NOT NULL PRIMARY KEY,
    type TEXT NOT NULL UNIQUE,
    enabled INTEGER DEFAULT 0 NOT NULL,
    profile_id VARCHAR(36) REFERENCES task_profiles(id) ON DELETE SET NULL,
    config TEXT,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL
)
"""

_LLM_PROVIDERS_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS llm_providers (
    id VARCHAR(36) NOT NULL PRIMARY KEY,
    name TEXT NOT NULL UNIQUE,
    base_url TEXT NOT NULL,
    api_key_encrypted TEXT NOT NULL,
    provider_type TEXT DEFAULT 'unknown' NOT NULL,
    is_default INTEGER DEFAULT 0 NOT NULL,
    source TEXT DEFAULT 'database' NOT NULL,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL
)
"""

_WEBHOOK_TRIGGERS_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS webhook_triggers (
    id VARCHAR(36) NOT NULL PRIMARY KEY,
    name TEXT NOT NULL UNIQUE,
    enabled INTEGER DEFAULT 1 NOT NULL,
    source TEXT NOT NULL,
    profile_id VARCHAR(36) REFERENCES task_profiles(id) ON DELETE SET NULL,
    filters TEXT DEFAULT '{}' NOT NULL,
    actions TEXT DEFAULT '{}' NOT NULL,
    task_prompt TEXT,
    webhook_secret TEXT,
    cloud_webhook_url TEXT,
    cloud_endpoint_token TEXT,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL
)
"""

_EXTERNAL_TASK_REFS_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS external_task_refs (
    id VARCHAR(36) NOT NULL PRIMARY KEY,
    task_id VARCHAR(36) NOT NULL UNIQUE REFERENCES tasks(id) ON DELETE CASCADE,
    trigger_id VARCHAR(36) REFERENCES webhook_triggers(id) ON DELETE SET NULL,
    source TEXT NOT NULL,
    external_id TEXT NOT NULL,
    external_url TEXT NOT NULL,
    parent_id TEXT,
    metadata TEXT DEFAULT '{}' NOT NULL,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL,
    UNIQUE(external_id, source)
)
"""

_MODEL_METADATA_CACHE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS model_metadata_cache (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    normalized_name TEXT NOT NULL UNIQUE,
    supports_reasoning BOOLEAN NOT NULL,
    max_output_tokens INTEGER,
    source_keys TEXT NOT NULL DEFAULT '[]',
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL
)
"""


async def _create_tables(engine):
    async with engine.begin() as conn:
        await conn.execute(text(_TASK_PROFILES_TABLE_SQL))
        await conn.execute(text(_TASKS_TABLE_SQL))
        await conn.execute(text(_SETTINGS_TABLE_SQL))
        await conn.execute(text(_TAGS_TABLE_SQL))
        await conn.execute(text(_TASK_TAGS_TABLE_SQL))
        await conn.execute(text(_PLATFORM_CREDENTIALS_TABLE_SQL))
        await conn.execute(text(_SKILLS_TABLE_SQL))
        await conn.execute(text(_SKILL_FILES_TABLE_SQL))
        await conn.execute(text(_LOCAL_USERS_TABLE_SQL))
        await conn.execute(text(_TASK_GENERATORS_TABLE_SQL))
        await conn.execute(text(_LLM_PROVIDERS_TABLE_SQL))
        await conn.execute(text(_WEBHOOK_TRIGGERS_TABLE_SQL))
        await conn.execute(text(_EXTERNAL_TASK_REFS_TABLE_SQL))
        await conn.execute(text(_MODEL_METADATA_CACHE_TABLE_SQL))
        await conn.execute(text(_MARKETPLACES_TABLE_SQL))
        await conn.execute(text(_PLUGINS_TABLE_SQL))
        await conn.execute(text(_EVAL_RUNS_TABLE_SQL))
        await conn.execute(text(_EVAL_RESULTS_TABLE_SQL))


@pytest.fixture()
async def fake_valkey() -> AsyncGenerator[FakeRedis, None]:
    redis = FakeRedis(decode_responses=True)
    events_module._valkey = redis
    yield redis
    events_module._valkey = None
    await redis.aclose()


@pytest.fixture()
async def client(fake_valkey) -> AsyncGenerator[AsyncClient, None]:
    engine = create_async_engine("sqlite+aiosqlite://", echo=False)
    await _create_tables(engine)

    test_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async def override_get_session():
        async with test_session() as session:
            yield session

    async def override_get_current_user():
        return FAKE_USER_CLAIMS

    async def override_require_editor():
        return FAKE_USER_CLAIMS

    app.dependency_overrides[get_session] = override_get_session
    app.dependency_overrides[get_current_user] = override_get_current_user
    app.dependency_overrides[require_editor] = override_require_editor

    # Non-admin: require_admin should reject
    from fastapi import HTTPException

    async def override_require_admin_reject():
        raise HTTPException(status_code=403, detail="Admin role required")

    app.dependency_overrides[require_admin] = override_require_admin_reject
    app.dependency_overrides[_tg_require_admin] = override_require_admin_reject
    app.dependency_overrides[_wt_require_admin] = override_require_admin_reject
    app.dependency_overrides[_jc_require_admin] = override_require_admin_reject
    app.dependency_overrides[_pl_require_admin] = override_require_admin_reject

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac

    app.dependency_overrides.clear()
    await engine.dispose()


@pytest.fixture()
async def admin_client_with_session(fake_valkey) -> AsyncGenerator[tuple[AsyncClient, async_sessionmaker], None]:
    """Admin client paired with the session_maker for direct DB access in tests."""
    engine = create_async_engine("sqlite+aiosqlite://", echo=False)
    await _create_tables(engine)

    test_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async def override_get_session():
        async with test_session() as session:
            yield session

    async def override_get_current_user():
        return FAKE_ADMIN_CLAIMS

    async def override_require_editor():
        return FAKE_ADMIN_CLAIMS

    async def override_require_admin():
        return FAKE_ADMIN_CLAIMS

    app.dependency_overrides[get_session] = override_get_session
    app.dependency_overrides[get_current_user] = override_get_current_user
    app.dependency_overrides[require_editor] = override_require_editor
    app.dependency_overrides[require_admin] = override_require_admin
    app.dependency_overrides[_tg_require_admin] = override_require_admin
    app.dependency_overrides[_wt_require_admin] = override_require_admin
    app.dependency_overrides[_jc_require_admin] = override_require_admin
    app.dependency_overrides[_pl_require_admin] = override_require_admin

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac, test_session

    app.dependency_overrides.clear()
    await engine.dispose()


@pytest.fixture()
async def admin_client(admin_client_with_session) -> AsyncGenerator[AsyncClient, None]:
    """Client authenticated as an admin user."""
    client, _ = admin_client_with_session
    yield client


@pytest.fixture()
async def unauth_client(fake_valkey) -> AsyncGenerator[AsyncClient, None]:
    """Client without auth override — requests will be rejected."""
    engine = create_async_engine("sqlite+aiosqlite://", echo=False)
    await _create_tables(engine)

    test_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async def override_get_session():
        async with test_session() as session:
            yield session

    app.dependency_overrides[get_session] = override_get_session
    app.dependency_overrides.pop(get_current_user, None)
    app.dependency_overrides.pop(require_editor, None)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac

    app.dependency_overrides.clear()
    await engine.dispose()


@pytest.fixture()
async def viewer_client(fake_valkey) -> AsyncGenerator[AsyncClient, None]:
    """Client authenticated as a viewer user (no editor/admin role)."""
    engine = create_async_engine("sqlite+aiosqlite://", echo=False)
    await _create_tables(engine)

    test_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async def override_get_session():
        async with test_session() as session:
            yield session

    async def override_get_current_user():
        return FAKE_VIEWER_CLAIMS

    from fastapi import HTTPException

    async def override_require_editor_reject():
        raise HTTPException(status_code=403, detail="Editor role required")

    async def override_require_admin_reject():
        raise HTTPException(status_code=403, detail="Admin role required")

    app.dependency_overrides[get_session] = override_get_session
    app.dependency_overrides[get_current_user] = override_get_current_user
    app.dependency_overrides[require_editor] = override_require_editor_reject
    app.dependency_overrides[require_admin] = override_require_admin_reject

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac

    app.dependency_overrides.clear()
    await engine.dispose()


@pytest.fixture()
async def db_session(fake_valkey):
    """Session factory + engine with database.async_session patched.

    Shared home for the fixture MCP/eval tool tests use to drive tools that call
    the module-level ``async_session`` directly (new_task, eval tools, etc.).
    Admin claims are injected so admin-guarded endpoints are reachable.
    """
    import database as database_module
    import mcp_server

    engine = create_async_engine("sqlite+aiosqlite://", echo=False)
    await _create_tables(engine)
    test_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    original = database_module.async_session
    database_module.async_session = test_session
    mcp_server.async_session = test_session

    async def override_get_session():
        async with test_session() as session:
            yield session

    app.dependency_overrides[get_session] = override_get_session
    app.dependency_overrides[get_current_user] = lambda: FAKE_ADMIN_CLAIMS
    app.dependency_overrides[require_editor] = lambda: FAKE_ADMIN_CLAIMS
    app.dependency_overrides[require_admin] = lambda: FAKE_ADMIN_CLAIMS

    yield engine, test_session

    app.dependency_overrides.clear()
    database_module.async_session = original
    mcp_server.async_session = original
    await engine.dispose()


@pytest.fixture()
async def admin_mcp_client(db_session) -> AsyncGenerator[AsyncClient, None]:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
