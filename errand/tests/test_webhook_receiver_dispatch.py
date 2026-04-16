"""Tests for B1 — webhook receiver keeps task refs and logs errors."""
import asyncio
import logging

import pytest

import webhook_receiver


async def test_dispatch_task_reference_kept_and_removed_on_success(monkeypatch):
    """Completed tasks are removed from the tracking set; no error logged."""
    started = asyncio.Event()

    async def _fake_dispatch(trigger, body, headers):
        started.set()
        await asyncio.sleep(0)

    monkeypatch.setattr(webhook_receiver, "_dispatch_webhook", _fake_dispatch)
    webhook_receiver._background_tasks.clear()

    # Simulate the dispatch pattern from receive_webhook()
    task = asyncio.create_task(webhook_receiver._dispatch_webhook(None, b"", {}))
    webhook_receiver._background_tasks.add(task)
    task.add_done_callback(webhook_receiver._on_dispatch_done)

    # Reference is retained while the task is in-flight.
    assert task in webhook_receiver._background_tasks

    # ``started`` fires partway through _fake_dispatch, so awaiting the event
    # alone does not guarantee the task has finished. Awaiting the task is
    # load-bearing — it joins execution and re-raises any unexpected error.
    await started.wait()
    await task

    # done_callback runs on the next loop tick.
    await asyncio.sleep(0)
    assert task not in webhook_receiver._background_tasks


async def test_dispatch_exception_is_logged_at_error(monkeypatch, caplog):
    """Raised exceptions are surfaced at ERROR level, not silently swallowed."""

    async def _boom(trigger, body, headers):
        raise RuntimeError("dispatch blew up")

    monkeypatch.setattr(webhook_receiver, "_dispatch_webhook", _boom)
    webhook_receiver._background_tasks.clear()

    with caplog.at_level(logging.ERROR, logger="webhook_receiver"):
        task = asyncio.create_task(webhook_receiver._dispatch_webhook(None, b"", {}))
        webhook_receiver._background_tasks.add(task)
        task.add_done_callback(webhook_receiver._on_dispatch_done)

        # Let the task run and the callback fire. The dispatch intentionally
        # raises; assert the exact error so we know we're exercising the real
        # failure path (not some other unexpected exception).
        with pytest.raises(RuntimeError, match="dispatch blew up"):
            await task
        await asyncio.sleep(0)

    assert task not in webhook_receiver._background_tasks
    error_records = [r for r in caplog.records if r.levelno == logging.ERROR]
    assert any("Webhook dispatch task failed" in r.getMessage() for r in error_records)
