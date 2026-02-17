"""Tests for Slack Block Kit message builders."""
import uuid
from datetime import datetime, timezone
from types import SimpleNamespace

from platforms.slack.blocks import (
    error_blocks,
    help_blocks,
    status_emoji,
    task_created_blocks,
    task_list_blocks,
    task_output_blocks,
    task_status_blocks,
)


def _make_task(**overrides):
    """Create a mock task object."""
    defaults = {
        "id": uuid.uuid4(),
        "title": "Test Task",
        "status": "pending",
        "category": "immediate",
        "created_at": datetime(2025, 1, 15, 12, 0, tzinfo=timezone.utc),
        "updated_at": datetime(2025, 1, 15, 12, 30, tzinfo=timezone.utc),
        "created_by": "test@example.com",
        "updated_by": None,
        "output": None,
        "description": None,
    }
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


class TestStatusEmoji:
    def test_new(self):
        assert status_emoji("new") == ":white_circle:"

    def test_scheduled(self):
        assert status_emoji("scheduled") == ":clock3:"

    def test_pending(self):
        assert status_emoji("pending") == ":hourglass_flowing_sand:"

    def test_running(self):
        assert status_emoji("running") == ":gear:"

    def test_review(self):
        assert status_emoji("review") == ":eyes:"

    def test_completed(self):
        assert status_emoji("completed") == ":white_check_mark:"

    def test_archived(self):
        assert status_emoji("archived") == ":file_cabinet:"

    def test_deleted(self):
        assert status_emoji("deleted") == ":wastebasket:"

    def test_unknown_status(self):
        assert status_emoji("unknown") == ":question:"


class TestTaskCreatedBlocks:
    def test_structure(self):
        task = _make_task()
        result = task_created_blocks(task)
        assert result["response_type"] == "ephemeral"
        assert len(result["blocks"]) == 3
        assert result["blocks"][0]["type"] == "header"
        assert result["blocks"][0]["text"]["text"] == "Task Created"
        assert result["blocks"][1]["type"] == "section"
        assert len(result["blocks"][1]["fields"]) == 4
        assert result["blocks"][2]["type"] == "context"

    def test_includes_task_id_prefix(self):
        task_id = uuid.uuid4()
        task = _make_task(id=task_id)
        result = task_created_blocks(task)
        fields_text = " ".join(f["text"] for f in result["blocks"][1]["fields"])
        assert str(task_id)[:8] in fields_text

    def test_includes_created_by(self):
        task = _make_task(created_by="alice@example.com")
        result = task_created_blocks(task)
        context_text = result["blocks"][2]["elements"][0]["text"]
        assert "alice@example.com" in context_text


class TestTaskStatusBlocks:
    def test_structure(self):
        task = _make_task()
        result = task_status_blocks(task)
        assert result["response_type"] == "ephemeral"
        assert result["blocks"][0]["type"] == "header"
        assert result["blocks"][0]["text"]["text"] == "Test Task"

    def test_includes_context_when_created_by(self):
        task = _make_task(created_by="bob@example.com")
        result = task_status_blocks(task)
        context_block = result["blocks"][-1]
        assert context_block["type"] == "context"
        assert "bob@example.com" in context_block["elements"][0]["text"]

    def test_no_context_when_no_user_info(self):
        task = _make_task(created_by=None, updated_by=None)
        result = task_status_blocks(task)
        assert all(b["type"] != "context" for b in result["blocks"])

    def test_includes_updated_by(self):
        task = _make_task(created_by="alice@example.com", updated_by="bob@example.com")
        result = task_status_blocks(task)
        context_text = result["blocks"][-1]["elements"][0]["text"]
        assert "alice@example.com" in context_text
        assert "bob@example.com" in context_text


class TestTaskListBlocks:
    def test_empty_list(self):
        result = task_list_blocks([])
        assert result["response_type"] == "ephemeral"
        assert result["blocks"][0]["text"]["text"] == "Tasks"
        assert "No tasks found" in result["blocks"][1]["text"]["text"]

    def test_with_status_filter(self):
        result = task_list_blocks([], status_filter="pending")
        assert result["blocks"][0]["text"]["text"] == "Tasks (pending)"

    def test_with_tasks(self):
        tasks = [_make_task(title=f"Task {i}") for i in range(3)]
        result = task_list_blocks(tasks)
        section_text = result["blocks"][1]["text"]["text"]
        for task in tasks:
            assert task.title in section_text

    def test_truncation_at_20(self):
        tasks = [_make_task(title=f"Task {i}") for i in range(25)]
        result = task_list_blocks(tasks)
        assert len(result["blocks"]) == 3
        context = result["blocks"][2]
        assert context["type"] == "context"
        assert "5 more" in context["elements"][0]["text"]

    def test_exactly_20_no_truncation(self):
        tasks = [_make_task(title=f"Task {i}") for i in range(20)]
        result = task_list_blocks(tasks)
        assert len(result["blocks"]) == 2

    def test_grouped_by_status(self):
        tasks = [
            _make_task(title="Pending A", status="pending"),
            _make_task(title="Pending B", status="pending"),
            _make_task(title="Running C", status="running"),
        ]
        result = task_list_blocks(tasks)
        # header + pending section + running section = 3 blocks
        assert len(result["blocks"]) == 3
        pending_text = result["blocks"][1]["text"]["text"]
        assert "Pending A" in pending_text
        assert "Pending B" in pending_text
        running_text = result["blocks"][2]["text"]["text"]
        assert "Running C" in running_text


class TestTaskOutputBlocks:
    def test_no_output(self):
        task = _make_task(output=None, status="review")
        result = task_output_blocks(task)
        assert result["response_type"] == "ephemeral"
        assert "no output yet" in result["blocks"][1]["text"]["text"]
        assert "review" in result["blocks"][1]["text"]["text"]

    def test_with_output(self):
        task = _make_task(output="Hello world")
        result = task_output_blocks(task)
        assert "Hello world" in result["blocks"][1]["text"]["text"]

    def test_output_truncation(self):
        long_output = "x" * 3500
        task = _make_task(output=long_output)
        result = task_output_blocks(task)
        text = result["blocks"][1]["text"]["text"]
        assert "truncated" in text
        assert len(text) < 3500

    def test_header_includes_title(self):
        task = _make_task(title="My Task")
        result = task_output_blocks(task)
        assert result["blocks"][0]["text"]["text"] == "Output: My Task"


class TestErrorBlocks:
    def test_structure(self):
        result = error_blocks("Something went wrong")
        assert result["response_type"] == "ephemeral"
        assert len(result["blocks"]) == 1
        assert ":warning:" in result["blocks"][0]["text"]["text"]
        assert "Something went wrong" in result["blocks"][0]["text"]["text"]


class TestHelpBlocks:
    def test_structure(self):
        result = help_blocks()
        assert result["response_type"] == "ephemeral"
        assert result["blocks"][0]["type"] == "header"
        assert result["blocks"][0]["text"]["text"] == "Task Commands"
        text = result["blocks"][1]["text"]["text"]
        assert "/task new" in text
        assert "/task status" in text
        assert "/task list" in text
        assert "/task run" in text
        assert "/task output" in text
        assert "/task help" in text
