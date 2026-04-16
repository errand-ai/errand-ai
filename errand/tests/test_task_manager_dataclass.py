"""Tests for B4 — processing coroutine receives a plain dataclass."""
import inspect
import uuid
from datetime import datetime
from unittest.mock import MagicMock

from task_manager import DequeuedTask, TaskManager


def test_dequeued_task_snapshot_from_orm_copies_scalars():
    """DequeuedTask.from_orm captures scalars without holding an ORM reference."""
    tag_a = MagicMock(id=uuid.uuid4())
    tag_b = MagicMock(id=uuid.uuid4())
    orm_task = MagicMock(
        id=uuid.uuid4(),
        title="clean up stale triggers",
        description="housekeeping",
        category="repeating",
        profile_id=uuid.uuid4(),
        repeat_interval="1d",
        repeat_until=datetime(2026, 6, 1),
        tags=[tag_a, tag_b],
    )

    snapshot = DequeuedTask.from_orm(orm_task)

    assert isinstance(snapshot, DequeuedTask)
    assert snapshot.id == orm_task.id
    assert snapshot.title == orm_task.title
    assert snapshot.description == orm_task.description
    assert snapshot.category == "repeating"
    assert snapshot.profile_id == orm_task.profile_id
    assert snapshot.repeat_interval == "1d"
    assert snapshot.tag_ids == [tag_a.id, tag_b.id]


def test_run_task_signature_accepts_dequeued_task():
    """The spawned processing coroutine takes the plain dataclass, not an ORM Task."""
    sig = inspect.signature(TaskManager._run_task)
    task_param = sig.parameters["task"]
    assert task_param.annotation is DequeuedTask


def test_process_task_signature_accepts_dequeued_task():
    """_process_task — the container entry point — also takes the plain dataclass."""
    sig = inspect.signature(TaskManager._process_task)
    assert sig.parameters["task"].annotation is DequeuedTask
