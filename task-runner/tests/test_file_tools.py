"""Tests for file tools: write_file, edit_file, read_file, and FileMutationQueue."""

import asyncio
import os
import tempfile

import pytest

from main import write_file, edit_file, read_file, FileMutationQueue


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

@pytest.fixture
def tmp_dir():
    """Provide a temporary directory that is cleaned up after the test."""
    with tempfile.TemporaryDirectory() as d:
        yield d


# ---------------------------------------------------------------------------
# 4.1 write_file — creates new file
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_write_file_creates_new_file(tmp_dir):
    """write_file creates a new file with correct content and returns byte count."""
    path = os.path.join(tmp_dir, "hello.txt")
    result = await write_file(path, "Hello, world!")
    assert "13 bytes" in result
    assert os.path.isfile(path)
    with open(path) as f:
        assert f.read() == "Hello, world!"


# ---------------------------------------------------------------------------
# 4.2 write_file — overwrites existing file
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_write_file_overwrites_existing(tmp_dir):
    """write_file overwrites an existing file."""
    path = os.path.join(tmp_dir, "overwrite.txt")
    with open(path, "w") as f:
        f.write("old content")
    result = await write_file(path, "new content")
    assert "11 bytes" in result
    with open(path) as f:
        assert f.read() == "new content"


# ---------------------------------------------------------------------------
# 4.3 write_file — creates parent directories
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_write_file_creates_parent_dirs(tmp_dir):
    """write_file creates parent directories if they don't exist."""
    path = os.path.join(tmp_dir, "a", "b", "c", "deep.txt")
    result = await write_file(path, "deep content")
    assert "bytes" in result
    assert os.path.isfile(path)
    with open(path) as f:
        assert f.read() == "deep content"


# ---------------------------------------------------------------------------
# 4.4 edit_file — replaces exact match and returns diff
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_edit_file_replaces_exact_match(tmp_dir):
    """edit_file replaces exact match and returns a unified diff."""
    path = os.path.join(tmp_dir, "edit.txt")
    with open(path, "w") as f:
        f.write("line one\nline two\nline three\n")
    result = await edit_file(path, "line two", "LINE TWO")
    # Should contain diff markers
    assert "---" in result
    assert "+++" in result
    assert "-line two" in result
    assert "+LINE TWO" in result
    # Verify file was actually modified
    with open(path) as f:
        assert f.read() == "line one\nLINE TWO\nline three\n"


# ---------------------------------------------------------------------------
# 4.5 edit_file — no match found
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_edit_file_no_match(tmp_dir):
    """edit_file returns error when old_text not found."""
    path = os.path.join(tmp_dir, "edit.txt")
    with open(path, "w") as f:
        f.write("hello world")
    result = await edit_file(path, "nonexistent text", "replacement")
    assert "Error" in result
    assert "no match" in result


# ---------------------------------------------------------------------------
# 4.6 edit_file — multiple matches found
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_edit_file_multiple_matches(tmp_dir):
    """edit_file returns error when old_text matches more than once."""
    path = os.path.join(tmp_dir, "edit.txt")
    with open(path, "w") as f:
        f.write("foo bar foo baz foo")
    result = await edit_file(path, "foo", "replaced")
    assert "Error" in result
    assert "3 matches" in result


# ---------------------------------------------------------------------------
# 4.7 edit_file — file does not exist
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_edit_file_not_found():
    """edit_file returns error when file does not exist."""
    result = await edit_file("/nonexistent/path/file.txt", "old", "new")
    assert "Error" in result
    assert "file not found" in result


# ---------------------------------------------------------------------------
# 4.8 read_file — returns content with line numbers
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_read_file_with_line_numbers(tmp_dir):
    """read_file returns content with line numbers prefixed."""
    path = os.path.join(tmp_dir, "read.txt")
    with open(path, "w") as f:
        f.write("alpha\nbeta\ngamma\n")
    result = await read_file(path)
    assert "1\talpha" in result
    assert "2\tbeta" in result
    assert "3\tgamma" in result


# ---------------------------------------------------------------------------
# 4.9 read_file — pagination with offset and limit
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_read_file_pagination(tmp_dir):
    """read_file respects offset and limit for pagination."""
    path = os.path.join(tmp_dir, "read.txt")
    with open(path, "w") as f:
        f.write("line0\nline1\nline2\nline3\nline4\n")
    result = await read_file(path, offset=1, limit=2)
    lines = result.strip().split("\n")
    assert len(lines) == 2
    assert "2\tline1" in lines[0]
    assert "3\tline2" in lines[1]


# ---------------------------------------------------------------------------
# 4.10 read_file — file does not exist
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_read_file_not_found():
    """read_file returns error when file does not exist."""
    result = await read_file("/nonexistent/path/file.txt")
    assert "Error" in result
    assert "file not found" in result


# ---------------------------------------------------------------------------
# 4.11 FileMutationQueue — serializes concurrent writes to the same path
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_mutation_queue_serializes_same_path(tmp_dir):
    """FileMutationQueue serializes concurrent writes to the same path."""
    path = os.path.join(tmp_dir, "concurrent.txt")
    queue = FileMutationQueue()
    order = []

    async def writer(label: str, delay: float):
        async with queue.acquire(path):
            order.append(f"{label}_start")
            await asyncio.sleep(delay)
            order.append(f"{label}_end")

    # Launch two concurrent writers for the same path
    await asyncio.gather(writer("A", 0.05), writer("B", 0.05))
    # They must be serialized: A completes before B starts (or vice versa)
    assert order[0].endswith("_start")
    assert order[1].endswith("_end")
    # Same writer must start and end consecutively
    assert order[0][0] == order[1][0]  # e.g. A_start, A_end
    assert order[2][0] == order[3][0]  # e.g. B_start, B_end


# ---------------------------------------------------------------------------
# FileMutationQueue — queued waiters serialize correctly with eviction
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_mutation_queue_queued_waiters_serialize(tmp_dir):
    """FileMutationQueue serializes queued acquires and evicts only when safe."""
    path = os.path.join(tmp_dir, "concurrent.txt")
    queue = FileMutationQueue()
    order = []

    first_acquired = asyncio.Event()
    first_can_release = asyncio.Event()
    second_acquired = asyncio.Event()
    second_can_release = asyncio.Event()

    async def first_writer():
        async with queue.acquire(path):
            order.append("A_start")
            first_acquired.set()
            await first_can_release.wait()
            order.append("A_end")

    async def second_writer():
        await first_acquired.wait()
        async with queue.acquire(path):
            order.append("B_start")
            second_acquired.set()
            await second_can_release.wait()
            order.append("B_end")

    async def third_writer():
        await second_acquired.wait()
        async with queue.acquire(path):
            order.append("C_start")
            order.append("C_end")

    first_task = asyncio.create_task(first_writer())
    second_task = asyncio.create_task(second_writer())

    await first_acquired.wait()
    # B is now waiting on the lock
    first_can_release.set()
    await second_acquired.wait()

    # Launch C while B holds the lock
    third_task = asyncio.create_task(third_writer())
    await asyncio.sleep(0)  # let C enqueue

    second_can_release.set()
    await asyncio.gather(first_task, second_task, third_task)

    assert order == ["A_start", "A_end", "B_start", "B_end", "C_start", "C_end"]


# ---------------------------------------------------------------------------
# 4.12 FileMutationQueue — allows concurrent writes to different paths
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_mutation_queue_allows_different_paths(tmp_dir):
    """FileMutationQueue allows concurrent writes to different paths."""
    path_a = os.path.join(tmp_dir, "a.txt")
    path_b = os.path.join(tmp_dir, "b.txt")
    queue = FileMutationQueue()
    order = []

    async def writer(label: str, path: str):
        async with queue.acquire(path):
            order.append(f"{label}_start")
            await asyncio.sleep(0.05)
            order.append(f"{label}_end")

    await asyncio.gather(writer("A", path_a), writer("B", path_b))
    # Both should start before either finishes (concurrent)
    starts = [e for e in order if e.endswith("_start")]
    ends = [e for e in order if e.endswith("_end")]
    # Both starts should come before both ends
    start_indices = [order.index(s) for s in starts]
    end_indices = [order.index(e) for e in ends]
    assert max(start_indices) < min(end_indices)
