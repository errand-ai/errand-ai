"""Tests for Task Profile CRUD API and task-profile association."""
import json
import uuid

import pytest
from unittest.mock import patch

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from models import Task, TaskProfile


@pytest.mark.asyncio
async def test_list_profiles_empty(admin_client):
    resp = await admin_client.get("/api/task-profiles")
    assert resp.status_code == 200
    assert resp.json() == []


@pytest.mark.asyncio
async def test_create_profile(admin_client):
    body = {"name": "email-triage", "model": {"provider_id": None, "model": "claude-haiku-4-5-20251001"}, "match_rules": "Tasks about email"}
    resp = await admin_client.post("/api/task-profiles", json=body)
    assert resp.status_code == 201
    data = resp.json()
    assert data["name"] == "email-triage"
    assert data["model"] == {"provider_id": None, "model": "claude-haiku-4-5-20251001"}
    assert data["match_rules"] == "Tasks about email"
    assert data["id"]  # UUID assigned


@pytest.mark.asyncio
async def test_create_profile_duplicate_name(admin_client):
    body = {"name": "dup-test"}
    await admin_client.post("/api/task-profiles", json=body)
    resp = await admin_client.post("/api/task-profiles", json=body)
    assert resp.status_code == 409


@pytest.mark.asyncio
async def test_create_profile_empty_name(admin_client):
    resp = await admin_client.post("/api/task-profiles", json={"name": ""})
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_create_profile_invalid_reasoning_effort(admin_client):
    resp = await admin_client.post("/api/task-profiles", json={"name": "test", "reasoning_effort": "maximum"})
    assert resp.status_code == 422
    assert "reasoning_effort" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_create_profile_valid_reasoning_effort(admin_client):
    for val in ("low", "medium", "high"):
        resp = await admin_client.post("/api/task-profiles", json={"name": f"re-{val}", "reasoning_effort": val})
        assert resp.status_code == 201
        assert resp.json()["reasoning_effort"] == val


@pytest.mark.asyncio
async def test_list_profiles_ordered_by_name(admin_client):
    await admin_client.post("/api/task-profiles", json={"name": "zebra"})
    await admin_client.post("/api/task-profiles", json={"name": "alpha"})
    resp = await admin_client.get("/api/task-profiles")
    names = [p["name"] for p in resp.json()]
    assert names == ["alpha", "zebra"]


@pytest.mark.asyncio
async def test_get_profile(admin_client):
    create_resp = await admin_client.post("/api/task-profiles", json={"name": "get-test"})
    pid = create_resp.json()["id"]
    resp = await admin_client.get(f"/api/task-profiles/{pid}")
    assert resp.status_code == 200
    assert resp.json()["name"] == "get-test"


@pytest.mark.asyncio
async def test_get_profile_not_found(admin_client):
    resp = await admin_client.get("/api/task-profiles/00000000-0000-0000-0000-000000000000")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_update_profile(admin_client):
    create_resp = await admin_client.post("/api/task-profiles", json={"name": "update-test", "model": {"provider_id": None, "model": "old-model"}})
    pid = create_resp.json()["id"]
    resp = await admin_client.put(f"/api/task-profiles/{pid}", json={"model": {"provider_id": None, "model": "new-model"}})
    assert resp.status_code == 200
    assert resp.json()["model"] == {"provider_id": None, "model": "new-model"}
    assert resp.json()["name"] == "update-test"  # unchanged


@pytest.mark.asyncio
async def test_update_profile_duplicate_name(admin_client):
    await admin_client.post("/api/task-profiles", json={"name": "existing"})
    create_resp = await admin_client.post("/api/task-profiles", json={"name": "rename-me"})
    pid = create_resp.json()["id"]
    resp = await admin_client.put(f"/api/task-profiles/{pid}", json={"name": "existing"})
    assert resp.status_code == 409


@pytest.mark.asyncio
async def test_update_profile_invalid_reasoning_effort(admin_client):
    create_resp = await admin_client.post("/api/task-profiles", json={"name": "re-update"})
    pid = create_resp.json()["id"]
    resp = await admin_client.put(f"/api/task-profiles/{pid}", json={"reasoning_effort": "extreme"})
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_delete_profile(admin_client):
    create_resp = await admin_client.post("/api/task-profiles", json={"name": "delete-me"})
    pid = create_resp.json()["id"]
    resp = await admin_client.delete(f"/api/task-profiles/{pid}")
    assert resp.status_code == 204
    # Verify gone
    get_resp = await admin_client.get(f"/api/task-profiles/{pid}")
    assert get_resp.status_code == 404


@pytest.mark.asyncio
async def test_delete_nonexistent_profile(admin_client):
    resp = await admin_client.delete("/api/task-profiles/00000000-0000-0000-0000-000000000000")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_create_profile_three_state_list_fields(admin_client):
    """Test null vs [] vs explicit list for mcp_servers."""
    # null (inherit)
    resp = await admin_client.post("/api/task-profiles", json={"name": "inherit-test", "mcp_servers": None})
    assert resp.status_code == 201
    assert resp.json()["mcp_servers"] is None

    # empty (none)
    resp = await admin_client.post("/api/task-profiles", json={"name": "empty-test", "mcp_servers": []})
    assert resp.status_code == 201
    assert resp.json()["mcp_servers"] == []

    # explicit
    resp = await admin_client.post("/api/task-profiles", json={"name": "explicit-test", "mcp_servers": ["gmail"]})
    assert resp.status_code == 201
    assert resp.json()["mcp_servers"] == ["gmail"]


@pytest.mark.asyncio
async def test_profiles_require_admin(client):
    """Non-admin users cannot access profile endpoints."""
    resp = await client.get("/api/task-profiles")
    assert resp.status_code == 403


# --- Task + Profile association ---


@pytest.mark.asyncio
async def test_task_response_includes_profile_fields(admin_client):
    """TaskResponse includes profile_id and profile_name."""
    resp = await admin_client.post("/api/tasks", json={"input": "Quick test"})
    assert resp.status_code == 201
    data = resp.json()
    assert "profile_id" in data
    assert "profile_name" in data
    assert data["profile_id"] is None
    assert data["profile_name"] is None


@pytest.mark.asyncio
async def test_patch_task_profile_id(admin_client):
    """Can set and clear profile_id via PATCH."""
    # Create a profile
    profile = (await admin_client.post("/api/task-profiles", json={"name": "patch-prof"})).json()
    pid = profile["id"]

    # Create a task
    task = (await admin_client.post("/api/tasks", json={"input": "Profile test"})).json()
    tid = task["id"]

    # Set profile
    resp = await admin_client.patch(f"/api/tasks/{tid}", json={"profile_id": pid})
    assert resp.status_code == 200
    assert resp.json()["profile_id"] == pid
    assert resp.json()["profile_name"] == "patch-prof"

    # Clear profile
    resp = await admin_client.patch(f"/api/tasks/{tid}", json={"profile_id": "null"})
    assert resp.status_code == 200
    assert resp.json()["profile_id"] is None
    assert resp.json()["profile_name"] is None


@pytest.mark.asyncio
async def test_patch_task_invalid_profile_id(admin_client):
    """PATCH with nonexistent profile_id returns 422."""
    task = (await admin_client.post("/api/tasks", json={"input": "Bad profile test"})).json()
    tid = task["id"]
    resp = await admin_client.patch(f"/api/tasks/{tid}", json={"profile_id": "00000000-0000-0000-0000-000000000000"})
    assert resp.status_code == 422


# --- 4.6: LLM Classification (profile selection during task creation) ---


@pytest.mark.asyncio
async def test_llm_classification_matching_profile(admin_client):
    """When LLM returns a profile name matching an existing profile, task gets that profile_id."""
    # Create a profile first
    profile_resp = await admin_client.post("/api/task-profiles", json={
        "name": "email-handler",
        "match_rules": "Tasks about email management",
    })
    assert profile_resp.status_code == 201
    profile_id = profile_resp.json()["id"]

    # Mock generate_title to return the profile name
    from llm import LLMResult
    mock_result = LLMResult(
        title="Process Inbox Emails",
        success=True,
        category="immediate",
        description="Go through all unread emails in my inbox and categorize them by priority",
        profile="email-handler",
    )

    with patch("main.generate_title", return_value=mock_result):
        resp = await admin_client.post("/api/tasks", json={
            "input": "Go through all unread emails in my inbox and categorize them by priority"
        })

    assert resp.status_code == 201
    data = resp.json()
    assert data["profile_id"] == profile_id
    assert data["profile_name"] == "email-handler"


@pytest.mark.asyncio
async def test_llm_classification_unknown_profile(admin_client):
    """When LLM returns an unknown profile name, profile_id is null."""
    # Create a real profile (so there are profiles in the DB)
    await admin_client.post("/api/task-profiles", json={"name": "real-profile"})

    from llm import LLMResult
    mock_result = LLMResult(
        title="Deploy Application",
        success=True,
        category="immediate",
        description="Deploy the latest version of the application to the staging environment",
        profile="nonexistent-profile",
    )

    with patch("main.generate_title", return_value=mock_result):
        resp = await admin_client.post("/api/tasks", json={
            "input": "Deploy the latest version of the application to the staging environment"
        })

    assert resp.status_code == 201
    data = resp.json()
    assert data["profile_id"] is None
    assert data["profile_name"] is None


@pytest.mark.asyncio
async def test_llm_classification_no_profiles_exist(admin_client):
    """When no profiles exist, task creation works normally with profile_id null."""
    from llm import LLMResult
    mock_result = LLMResult(
        title="Update Dependencies",
        success=True,
        category="immediate",
        description="Update all npm dependencies in the frontend project to their latest versions",
        profile=None,
    )

    with patch("main.generate_title", return_value=mock_result):
        resp = await admin_client.post("/api/tasks", json={
            "input": "Update all npm dependencies in the frontend project to their latest versions"
        })

    assert resp.status_code == 201
    data = resp.json()
    assert data["profile_id"] is None
    assert data["profile_name"] is None


@pytest.mark.asyncio
async def test_llm_classification_short_input_no_profile(admin_client):
    """When LLM fails (short input), profile_id is null."""
    # Create a profile to verify it's not accidentally assigned
    await admin_client.post("/api/task-profiles", json={"name": "some-profile"})

    # Short input (<=5 words) bypasses LLM entirely
    resp = await admin_client.post("/api/tasks", json={"input": "Fix bug"})

    assert resp.status_code == 201
    data = resp.json()
    assert data["profile_id"] is None
    assert data["profile_name"] is None


# --- 5.4: MCP schedule_task with profile parameter ---


@pytest.fixture()
async def mcp_db_session(fake_valkey):
    """Provides a session factory for MCP tool tests with patched database.async_session."""
    import database as database_module
    import mcp_server
    from main import app, get_current_user, require_editor, require_admin

    engine = create_async_engine("sqlite+aiosqlite://", echo=False)

    _tables_sql = [
        """CREATE TABLE IF NOT EXISTS task_profiles (
            id VARCHAR(36) NOT NULL PRIMARY KEY,
            name TEXT NOT NULL UNIQUE,
            description TEXT,
            match_rules TEXT,
            model TEXT,
            system_prompt TEXT,
            max_turns INTEGER,
            reasoning_effort TEXT,
            mcp_servers TEXT,
            litellm_mcp_servers TEXT,
            skill_ids TEXT,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL,
            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL
        )""",
        """CREATE TABLE IF NOT EXISTS tasks (
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
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL,
            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL
        )""",
        """CREATE TABLE IF NOT EXISTS settings (
            key TEXT NOT NULL PRIMARY KEY,
            value TEXT NOT NULL,
            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL
        )""",
        """CREATE TABLE IF NOT EXISTS tags (
            id VARCHAR(36) NOT NULL PRIMARY KEY,
            name TEXT NOT NULL UNIQUE
        )""",
        """CREATE TABLE IF NOT EXISTS task_tags (
            task_id VARCHAR(36) NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
            tag_id VARCHAR(36) NOT NULL REFERENCES tags(id) ON DELETE CASCADE,
            PRIMARY KEY (task_id, tag_id)
        )""",
        """CREATE TABLE IF NOT EXISTS platform_credentials (
            platform_id TEXT NOT NULL PRIMARY KEY,
            encrypted_data TEXT NOT NULL,
            status TEXT DEFAULT 'disconnected' NOT NULL,
            last_verified_at DATETIME,
            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL
        )""",
    ]

    async with engine.begin() as conn:
        for sql in _tables_sql:
            await conn.execute(text(sql))

    test_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    original_db = database_module.async_session
    original_mcp = mcp_server.async_session
    database_module.async_session = test_session
    mcp_server.async_session = test_session

    yield engine, test_session

    database_module.async_session = original_db
    mcp_server.async_session = original_mcp
    await engine.dispose()


@pytest.mark.asyncio
async def test_schedule_task_with_valid_profile(mcp_db_session):
    """schedule_task with valid profile name sets profile_id on the task."""
    engine, session_factory = mcp_db_session

    # Create a profile using ORM for UUID consistency
    async with session_factory() as session:
        profile = TaskProfile(name="deploy-profile")
        session.add(profile)
        await session.commit()
        await session.refresh(profile)
        profile_id = profile.id

    from mcp_server import schedule_task
    task_uuid = await schedule_task(
        description="Deploy app",
        execute_at="2026-03-01T09:00:00Z",
        profile="deploy-profile",
    )

    assert len(task_uuid) == 36

    async with session_factory() as session:
        result = await session.execute(select(Task).where(Task.id == uuid.UUID(task_uuid)))
        task = result.scalar_one()
        assert task.profile_id == profile_id


@pytest.mark.asyncio
async def test_schedule_task_without_profile(mcp_db_session):
    """schedule_task without profile parameter creates task with null profile_id."""
    engine, session_factory = mcp_db_session

    from mcp_server import schedule_task
    task_uuid = await schedule_task(
        description="Check logs",
        execute_at="2026-03-01T09:00:00Z",
    )

    assert len(task_uuid) == 36

    async with session_factory() as session:
        result = await session.execute(select(Task).where(Task.id == uuid.UUID(task_uuid)))
        task = result.scalar_one()
        assert task.profile_id is None


@pytest.mark.asyncio
async def test_schedule_task_unknown_profile(mcp_db_session):
    """schedule_task with unknown profile name returns error string."""
    from mcp_server import schedule_task
    result = await schedule_task(
        description="Send report",
        execute_at="2026-03-01T09:00:00Z",
        profile="nonexistent-profile",
    )

    assert isinstance(result, str)
    assert "Error" in result
    assert "nonexistent-profile" in result
    assert "not found" in result.lower()


# --- 6.12: Worker resolve_profile tests ---


@pytest.fixture()
async def worker_db_session():
    """Create an in-memory SQLite session with task_profiles and tasks tables for worker tests."""
    engine = create_async_engine("sqlite+aiosqlite://", echo=False)

    async with engine.begin() as conn:
        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS task_profiles (
                id VARCHAR(36) NOT NULL PRIMARY KEY,
                name TEXT NOT NULL UNIQUE,
                description TEXT,
                match_rules TEXT,
                model TEXT,
                system_prompt TEXT,
                max_turns INTEGER,
                reasoning_effort TEXT,
                mcp_servers TEXT,
                litellm_mcp_servers TEXT,
                skill_ids TEXT,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL
            )
        """))
        await conn.execute(text("""
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
                profile_id VARCHAR(36),
                created_by TEXT,
                updated_by TEXT,
        encrypted_env TEXT,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL
            )
        """))
        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS settings (
                key TEXT NOT NULL PRIMARY KEY,
                value TEXT NOT NULL,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL
            )
        """))
        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS tags (
                id VARCHAR(36) NOT NULL PRIMARY KEY,
                name TEXT NOT NULL UNIQUE
            )
        """))
        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS task_tags (
                task_id VARCHAR(36) NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
                tag_id VARCHAR(36) NOT NULL REFERENCES tags(id) ON DELETE CASCADE,
                PRIMARY KEY (task_id, tag_id)
            )
        """))

    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with session_factory() as session:
        yield session

    await engine.dispose()


@pytest.mark.asyncio
async def test_resolve_profile_with_profile(worker_db_session):
    """Task with profile overrides settings with profile values."""
    from task_manager import _resolve_profile as resolve_profile

    session = worker_db_session

    # Create a profile using ORM (ensures UUID type consistency)
    profile = TaskProfile(name="custom-profile", model={"provider_id": None, "model": "gpt-4o"}, system_prompt="You are a helpful assistant.")
    session.add(profile)
    await session.commit()
    await session.refresh(profile)

    # Create a task with that profile
    task = Task(title="Test", description="Test task", status="pending", category="immediate")
    task.profile_id = profile.id
    session.add(task)
    await session.commit()
    await session.refresh(task)

    settings = {"task_processing_model": "claude-haiku", "system_prompt": "default prompt"}
    resolved = await resolve_profile(session, task, settings)

    assert resolved["task_processing_model"] == {"provider_id": None, "model": "gpt-4o"}
    assert resolved["system_prompt"] == "You are a helpful assistant."
    # Original settings dict should not be mutated
    assert settings["task_processing_model"] == "claude-haiku"
    assert settings["system_prompt"] == "default prompt"


@pytest.mark.asyncio
async def test_resolve_profile_without_profile(worker_db_session):
    """Task without profile returns settings unchanged."""
    from task_manager import _resolve_profile as resolve_profile

    session = worker_db_session

    task = Task(title="Test", description="Test task", status="pending", category="immediate")
    session.add(task)
    await session.commit()
    await session.refresh(task)

    settings = {"task_processing_model": "claude-haiku", "system_prompt": "default"}
    resolved = await resolve_profile(session, task, settings)

    assert resolved is settings  # same object, not a copy
    assert resolved["task_processing_model"] == "claude-haiku"
    assert resolved["system_prompt"] == "default"


@pytest.mark.asyncio
async def test_resolve_profile_deleted_profile(worker_db_session):
    """Task referencing a deleted profile returns settings unchanged with warning."""
    from task_manager import _resolve_profile as resolve_profile

    session = worker_db_session

    # Create task with a profile_id that doesn't exist in the DB
    fake_profile_id = uuid.uuid4()
    task = Task(title="Test", description="Test task", status="pending", category="immediate")
    task.profile_id = fake_profile_id
    session.add(task)
    await session.commit()
    await session.refresh(task)

    settings = {"task_processing_model": "claude-haiku", "key": "value"}
    resolved = await resolve_profile(session, task, settings)

    assert resolved is settings  # unchanged
    assert resolved["task_processing_model"] == "claude-haiku"


@pytest.mark.asyncio
async def test_resolve_profile_override_model(worker_db_session):
    """Profile model overrides task_processing_model setting."""
    from task_manager import _resolve_profile as resolve_profile

    session = worker_db_session

    profile = TaskProfile(name="model-override", model={"provider_id": None, "model": "gpt-4-turbo"})
    session.add(profile)
    await session.commit()
    await session.refresh(profile)

    task = Task(title="Test", status="pending", category="immediate")
    task.profile_id = profile.id
    session.add(task)
    await session.commit()
    await session.refresh(task)

    settings = {"task_processing_model": "claude-haiku"}
    resolved = await resolve_profile(session, task, settings)
    assert resolved["task_processing_model"] == {"provider_id": None, "model": "gpt-4-turbo"}


@pytest.mark.asyncio
async def test_resolve_profile_override_system_prompt(worker_db_session):
    """Profile system_prompt overrides the system_prompt setting."""
    from task_manager import _resolve_profile as resolve_profile

    session = worker_db_session

    profile = TaskProfile(name="prompt-override", system_prompt="You are a code reviewer.")
    session.add(profile)
    await session.commit()
    await session.refresh(profile)

    task = Task(title="Test", status="pending", category="immediate")
    task.profile_id = profile.id
    session.add(task)
    await session.commit()
    await session.refresh(task)

    settings = {"system_prompt": "You are a general assistant."}
    resolved = await resolve_profile(session, task, settings)
    assert resolved["system_prompt"] == "You are a code reviewer."


@pytest.mark.asyncio
async def test_resolve_profile_override_max_turns(worker_db_session):
    """Profile max_turns is stored as _profile_max_turns string."""
    from task_manager import _resolve_profile as resolve_profile

    session = worker_db_session

    profile = TaskProfile(name="turns-override", max_turns=10)
    session.add(profile)
    await session.commit()
    await session.refresh(profile)

    task = Task(title="Test", status="pending", category="immediate")
    task.profile_id = profile.id
    session.add(task)
    await session.commit()
    await session.refresh(task)

    settings = {}
    resolved = await resolve_profile(session, task, settings)
    assert resolved["_profile_max_turns"] == "10"


@pytest.mark.asyncio
async def test_resolve_profile_override_reasoning_effort(worker_db_session):
    """Profile reasoning_effort is stored as _profile_reasoning_effort."""
    from task_manager import _resolve_profile as resolve_profile

    session = worker_db_session

    profile = TaskProfile(name="effort-override", reasoning_effort="high")
    session.add(profile)
    await session.commit()
    await session.refresh(profile)

    task = Task(title="Test", status="pending", category="immediate")
    task.profile_id = profile.id
    session.add(task)
    await session.commit()
    await session.refresh(task)

    settings = {}
    resolved = await resolve_profile(session, task, settings)
    assert resolved["_profile_reasoning_effort"] == "high"


@pytest.mark.asyncio
async def test_resolve_profile_mcp_servers_null_inherits(worker_db_session):
    """Profile with null mcp_servers does not add _profile_mcp_servers key (inherit)."""
    from task_manager import _resolve_profile as resolve_profile

    session = worker_db_session

    profile = TaskProfile(name="mcp-null")
    session.add(profile)
    await session.commit()
    await session.refresh(profile)

    task = Task(title="Test", status="pending", category="immediate")
    task.profile_id = profile.id
    session.add(task)
    await session.commit()
    await session.refresh(task)

    settings = {"some_key": "some_value"}
    resolved = await resolve_profile(session, task, settings)
    assert "_profile_mcp_servers" not in resolved


@pytest.mark.asyncio
async def test_resolve_profile_mcp_servers_empty_list(worker_db_session):
    """Profile with [] mcp_servers sets _profile_mcp_servers to empty list."""
    from task_manager import _resolve_profile as resolve_profile

    session = worker_db_session

    profile = TaskProfile(name="mcp-empty", mcp_servers=[])
    session.add(profile)
    await session.commit()
    await session.refresh(profile)

    task = Task(title="Test", status="pending", category="immediate")
    task.profile_id = profile.id
    session.add(task)
    await session.commit()
    await session.refresh(task)

    settings = {}
    resolved = await resolve_profile(session, task, settings)
    assert resolved["_profile_mcp_servers"] == []


@pytest.mark.asyncio
async def test_resolve_profile_mcp_servers_explicit(worker_db_session):
    """Profile with explicit mcp_servers sets _profile_mcp_servers to that list."""
    from task_manager import _resolve_profile as resolve_profile

    session = worker_db_session

    profile = TaskProfile(name="mcp-explicit", mcp_servers=["gmail", "calendar"])
    session.add(profile)
    await session.commit()
    await session.refresh(profile)

    task = Task(title="Test", status="pending", category="immediate")
    task.profile_id = profile.id
    session.add(task)
    await session.commit()
    await session.refresh(task)

    settings = {}
    resolved = await resolve_profile(session, task, settings)
    assert resolved["_profile_mcp_servers"] == ["gmail", "calendar"]


@pytest.mark.asyncio
async def test_resolve_profile_litellm_mcp_servers(worker_db_session):
    """Profile litellm_mcp_servers is stored as _profile_litellm_mcp_servers."""
    from task_manager import _resolve_profile as resolve_profile

    session = worker_db_session

    profile = TaskProfile(name="litellm-override", litellm_mcp_servers=["litellm-svc"])
    session.add(profile)
    await session.commit()
    await session.refresh(profile)

    task = Task(title="Test", status="pending", category="immediate")
    task.profile_id = profile.id
    session.add(task)
    await session.commit()
    await session.refresh(task)

    settings = {}
    resolved = await resolve_profile(session, task, settings)
    assert resolved["_profile_litellm_mcp_servers"] == ["litellm-svc"]


@pytest.mark.asyncio
async def test_resolve_profile_skill_ids(worker_db_session):
    """Profile skill_ids is stored as _profile_skill_ids."""
    from task_manager import _resolve_profile as resolve_profile

    session = worker_db_session

    skill_id_1 = str(uuid.uuid4())
    skill_id_2 = str(uuid.uuid4())
    profile = TaskProfile(name="skills-override", skill_ids=[skill_id_1, skill_id_2])
    session.add(profile)
    await session.commit()
    await session.refresh(profile)

    task = Task(title="Test", status="pending", category="immediate")
    task.profile_id = profile.id
    session.add(task)
    await session.commit()
    await session.refresh(task)

    settings = {}
    resolved = await resolve_profile(session, task, settings)
    assert resolved["_profile_skill_ids"] == [skill_id_1, skill_id_2]
