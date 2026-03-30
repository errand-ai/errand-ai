"""Tests for WebhookTrigger and ExternalTaskRef models."""

import uuid

import pytest
from sqlalchemy import event, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from tests.conftest import _create_tables


@pytest.fixture()
async def db_session():
    engine = create_async_engine("sqlite+aiosqlite://", echo=False)

    # Enable foreign keys for SQLite
    @event.listens_for(engine.sync_engine, "connect")
    def _set_sqlite_pragma(dbapi_conn, connection_record):
        cursor = dbapi_conn.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    await _create_tables(engine)
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with session_factory() as session:
        yield session
    await engine.dispose()


async def _insert_profile(session, profile_id=None):
    pid = profile_id or str(uuid.uuid4())
    await session.execute(text(
        "INSERT INTO task_profiles (id, name) VALUES (:id, :name)"
    ), {"id": pid, "name": f"profile-{pid[:8]}"})
    await session.commit()
    return pid


async def _insert_trigger(session, name="Test Trigger", source="jira", profile_id=None, secret=None):
    tid = str(uuid.uuid4())
    await session.execute(text(
        "INSERT INTO webhook_triggers (id, name, source, profile_id, webhook_secret) "
        "VALUES (:id, :name, :source, :profile_id, :secret)"
    ), {"id": tid, "name": name, "source": source, "profile_id": profile_id, "secret": secret})
    await session.commit()
    return tid


async def _insert_task(session, title="Test Task"):
    tid = str(uuid.uuid4())
    await session.execute(text(
        "INSERT INTO tasks (id, title, status) VALUES (:id, :title, 'pending')"
    ), {"id": tid, "title": title})
    await session.commit()
    return tid


async def _insert_ref(session, task_id, trigger_id=None, source="jira", external_id="PROJ-1", external_url="https://example.com"):
    rid = str(uuid.uuid4())
    await session.execute(text(
        "INSERT INTO external_task_refs (id, task_id, trigger_id, source, external_id, external_url) "
        "VALUES (:id, :task_id, :trigger_id, :source, :external_id, :external_url)"
    ), {"id": rid, "task_id": task_id, "trigger_id": trigger_id, "source": source,
        "external_id": external_id, "external_url": external_url})
    await session.commit()
    return rid


@pytest.mark.asyncio
class TestWebhookTriggerModel:
    async def test_create_minimal_trigger(self, db_session):
        tid = await _insert_trigger(db_session, name="My Trigger", source="jira")
        result = await db_session.execute(text("SELECT * FROM webhook_triggers WHERE id = :id"), {"id": tid})
        row = result.mappings().one()
        assert row["name"] == "My Trigger"
        assert row["source"] == "jira"
        assert row["enabled"] == 1  # SQLite boolean

    async def test_name_uniqueness(self, db_session):
        await _insert_trigger(db_session, name="Unique Name")
        with pytest.raises(Exception):  # IntegrityError
            await _insert_trigger(db_session, name="Unique Name")

    async def test_profile_relationship_nullable(self, db_session):
        tid = await _insert_trigger(db_session, profile_id=None)
        result = await db_session.execute(text("SELECT profile_id FROM webhook_triggers WHERE id = :id"), {"id": tid})
        row = result.mappings().one()
        assert row["profile_id"] is None

    async def test_profile_relationship_valid(self, db_session):
        pid = await _insert_profile(db_session)
        tid = await _insert_trigger(db_session, profile_id=pid)
        result = await db_session.execute(text("SELECT profile_id FROM webhook_triggers WHERE id = :id"), {"id": tid})
        row = result.mappings().one()
        assert row["profile_id"] == pid


@pytest.mark.asyncio
class TestExternalTaskRefModel:
    async def test_create_ref(self, db_session):
        task_id = await _insert_task(db_session)
        trigger_id = await _insert_trigger(db_session)
        rid = await _insert_ref(db_session, task_id=task_id, trigger_id=trigger_id)
        result = await db_session.execute(text("SELECT * FROM external_task_refs WHERE id = :id"), {"id": rid})
        row = result.mappings().one()
        assert row["source"] == "jira"
        assert row["external_id"] == "PROJ-1"

    async def test_deduplication_constraint(self, db_session):
        task1 = await _insert_task(db_session, title="Task 1")
        task2 = await _insert_task(db_session, title="Task 2")
        await _insert_ref(db_session, task_id=task1, source="jira", external_id="PROJ-1")
        with pytest.raises(Exception):  # IntegrityError — same (external_id, source)
            await _insert_ref(db_session, task_id=task2, source="jira", external_id="PROJ-1")

    async def test_different_source_same_external_id_allowed(self, db_session):
        task1 = await _insert_task(db_session, title="Task 1")
        task2 = await _insert_task(db_session, title="Task 2")
        await _insert_ref(db_session, task_id=task1, source="jira", external_id="PROJ-1")
        # Same external_id but different source — should succeed
        await _insert_ref(db_session, task_id=task2, source="github", external_id="PROJ-1")

    async def test_task_cascade_delete(self, db_session):
        task_id = await _insert_task(db_session)
        await _insert_ref(db_session, task_id=task_id)
        # Delete the task — ref should cascade
        await db_session.execute(text("DELETE FROM tasks WHERE id = :id"), {"id": task_id})
        await db_session.commit()
        result = await db_session.execute(text("SELECT COUNT(*) as cnt FROM external_task_refs WHERE task_id = :id"), {"id": task_id})
        assert result.mappings().one()["cnt"] == 0

    async def test_trigger_delete_nullifies_ref(self, db_session):
        task_id = await _insert_task(db_session)
        trigger_id = await _insert_trigger(db_session)
        await _insert_ref(db_session, task_id=task_id, trigger_id=trigger_id)
        # Delete the trigger — ref's trigger_id should be set to null
        await db_session.execute(text("DELETE FROM webhook_triggers WHERE id = :id"), {"id": trigger_id})
        await db_session.commit()
        result = await db_session.execute(text("SELECT trigger_id FROM external_task_refs WHERE task_id = :id"), {"id": task_id})
        row = result.mappings().one()
        assert row["trigger_id"] is None

    async def test_unique_task_id(self, db_session):
        task_id = await _insert_task(db_session)
        await _insert_ref(db_session, task_id=task_id, external_id="PROJ-1")
        with pytest.raises(Exception):  # IntegrityError — same task_id
            await _insert_ref(db_session, task_id=task_id, external_id="PROJ-2")
