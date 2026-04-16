"""Tests for B3 — scheduler.release_lock is a conditional no-op.

Uses a hand-rolled fake valkey that implements the ``EVAL`` check-and-delete
contract, because fakeredis does not ship Lua scripting support.
"""
import socket

import pytest

import events as events_module
import scheduler


class _FakeLuaValkey:
    """Minimal valkey stand-in with enough semantics to exercise release_lock.

    Implements ``execute_command("EVAL", script, 1, key, value)`` as if the
    Lua script were: ``GET == ARGV[1] ? DEL : 0``. We do not parse the script
    — we just honour the contract the real script enforces.
    """

    def __init__(self):
        self._store: dict[str, str] = {}

    async def set(self, key: str, value: str) -> None:
        self._store[key] = value

    async def get(self, key: str):
        return self._store.get(key)

    async def execute_command(self, *args):
        if args[0] != "EVAL":
            raise AssertionError(f"unexpected command: {args[0]}")
        _, _script, _numkeys, key, expected_value = args
        if self._store.get(key) == expected_value:
            self._store.pop(key, None)
            return 1
        return 0


@pytest.fixture()
def fake_valkey():
    fake = _FakeLuaValkey()
    events_module._valkey = fake
    yield fake
    events_module._valkey = None


async def test_release_lock_deletes_when_holder_matches(fake_valkey):
    """When our hostname still owns the lock, release deletes it."""
    await fake_valkey.set(scheduler.LOCK_KEY, socket.gethostname())

    await scheduler.release_lock()

    assert await fake_valkey.get(scheduler.LOCK_KEY) is None


async def test_release_lock_is_noop_when_value_mismatches(fake_valkey):
    """When another replica has taken the lock, release does not touch it."""
    await fake_valkey.set(scheduler.LOCK_KEY, "other-replica")

    await scheduler.release_lock()

    # Still held by the other replica — we did not clobber it.
    assert await fake_valkey.get(scheduler.LOCK_KEY) == "other-replica"


async def test_release_lock_is_noop_when_absent(fake_valkey):
    """Nothing to delete and no exception."""
    await scheduler.release_lock()
    assert await fake_valkey.get(scheduler.LOCK_KEY) is None
