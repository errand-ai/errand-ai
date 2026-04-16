"""Tests for GitHub dispatch in ExternalStatusUpdater."""

import uuid

import pytest

from unittest.mock import AsyncMock, MagicMock, patch

from external_status_updater import _dispatch_github, _parse_structured_output


@pytest.fixture(autouse=True)
def _ensure_encryption_key(monkeypatch):
    monkeypatch.setenv("CREDENTIAL_ENCRYPTION_KEY", "QqXQtnJMYRkG519FlL64LIGn3R_DvpZfeGgrWcHJV_w=")


def _make_ref(external_id="org/repo#42", source="github", trigger_id=None, metadata=None):
    ref = MagicMock()
    ref.id = uuid.uuid4()
    ref.task_id = uuid.uuid4()
    ref.trigger_id = trigger_id or uuid.uuid4()
    ref.source = source
    ref.external_id = external_id
    ref.external_url = "https://github.com/org/repo/issues/42"
    ref.metadata_ = metadata or {
        "project_node_id": "PVT_proj1",
        "item_node_id": "PVTI_item1",
        "content_node_id": "I_issue1",
        "repo_owner": "org",
        "repo_name": "repo",
    }
    return ref


def _make_trigger(actions=None):
    trigger = MagicMock()
    trigger.id = uuid.uuid4()
    trigger.actions = actions or {}
    return trigger


@pytest.mark.asyncio
class TestDispatchGitHub:
    async def test_running_with_column_on_running(self):
        ref = _make_ref()
        trigger = _make_trigger(actions={
            "column_on_running": "In Progress",
            "column_options": {"In Progress": "opt_inprogress"},
            "project_field_id": "PVTSSF_field1",
        })
        session = AsyncMock()

        with patch("external_status_updater.GitHubClient") as MockClient:
            mock_client = AsyncMock()
            MockClient.from_credentials = AsyncMock(return_value=mock_client)

            await _dispatch_github(
                ref, trigger, trigger.actions,
                {"id": str(ref.task_id), "status": "running"},
                "running", "", session,
            )

        mock_client.update_item_status.assert_called_once_with(
            "PVT_proj1", "PVTI_item1", "PVTSSF_field1", "opt_inprogress",
        )

    async def test_running_with_add_comment(self):
        ref = _make_ref()
        trigger = _make_trigger(actions={"add_comment": True})
        session = AsyncMock()

        with patch("external_status_updater.GitHubClient") as MockClient:
            mock_client = AsyncMock()
            MockClient.from_credentials = AsyncMock(return_value=mock_client)

            await _dispatch_github(
                ref, trigger, trigger.actions,
                {"id": str(ref.task_id), "status": "running"},
                "running", "", session,
            )

        mock_client.add_comment.assert_called_once()
        assert "started" in mock_client.add_comment.call_args[0][1].lower()

    async def test_completed_with_comment_output_structured(self):
        ref = _make_ref()
        trigger = _make_trigger(actions={"comment_output": True})
        session = AsyncMock()

        output = 'Some preamble\n```json\n{"summary": "Created PR #5", "status": "completed"}\n```'

        with patch("external_status_updater.GitHubClient") as MockClient:
            mock_client = AsyncMock()
            MockClient.from_credentials = AsyncMock(return_value=mock_client)

            await _dispatch_github(
                ref, trigger, trigger.actions,
                {"id": str(ref.task_id), "status": "completed", "output": output},
                "completed", output, session,
            )

        mock_client.add_comment.assert_called_once()
        comment = mock_client.add_comment.call_args[0][1]
        assert "Created PR #5" in comment
        assert "completed" in comment.lower()

    async def test_completed_with_copilot_review(self):
        ref = _make_ref()
        trigger = _make_trigger(actions={"copilot_review": True})
        session = AsyncMock()

        output = '```json\n{"pr_number": 99, "status": "completed"}\n```'

        with patch("external_status_updater.GitHubClient") as MockClient:
            mock_client = AsyncMock()
            MockClient.from_credentials = AsyncMock(return_value=mock_client)

            await _dispatch_github(
                ref, trigger, trigger.actions,
                {"id": str(ref.task_id), "status": "completed", "output": output},
                "completed", output, session,
            )

        mock_client.request_review.assert_called_once_with("org", "repo", 99, ["copilot"])

    async def test_completed_with_review_profile_id(self):
        ref = _make_ref()
        review_profile = uuid.uuid4()
        trigger = _make_trigger(actions={"review_profile_id": str(review_profile)})
        session = AsyncMock()

        output = '```json\n{"pr_url": "https://github.com/org/repo/pull/10", "pr_number": 10, "branch": "feature-x", "status": "completed"}\n```'

        with patch("external_status_updater.GitHubClient") as MockClient:
            mock_client = AsyncMock()
            MockClient.from_credentials = AsyncMock(return_value=mock_client)

            await _dispatch_github(
                ref, trigger, trigger.actions,
                {"id": str(ref.task_id), "status": "completed", "output": output},
                "completed", output, session,
            )

        # Should have added a Task and an ExternalTaskRef
        assert session.add.call_count == 2
        added_objects = [call.args[0] for call in session.add.call_args_list]
        from models import Task, ExternalTaskRef
        task_obj = next(o for o in added_objects if isinstance(o, Task))
        ref_obj = next(o for o in added_objects if isinstance(o, ExternalTaskRef))

        assert "Review:" in task_obj.title
        assert "org/repo#10" in task_obj.title
        assert task_obj.profile_id == review_profile
        assert ref_obj.source == "github"
        assert ref_obj.external_id != ref.external_id  # unique external_id for review
        session.commit.assert_called()

    async def test_completed_aborted_posts_reason_no_review_or_column(self):
        ref = _make_ref()
        trigger = _make_trigger(actions={
            "add_comment": True,
            "copilot_review": True,
            "column_on_complete": "Done",
            "column_options": {"Done": "opt_done"},
            "project_field_id": "PVTSSF_field1",
        })
        session = AsyncMock()

        output = '```json\n{"status": "aborted", "reason": "No actionable work found"}\n```'

        with patch("external_status_updater.GitHubClient") as MockClient:
            mock_client = AsyncMock()
            MockClient.from_credentials = AsyncMock(return_value=mock_client)

            await _dispatch_github(
                ref, trigger, trigger.actions,
                {"id": str(ref.task_id), "status": "completed", "output": output},
                "completed", output, session,
            )

        # Should post abort comment
        assert mock_client.add_comment.call_count == 1
        comment = mock_client.add_comment.call_args[0][1]
        assert "aborted" in comment.lower()
        assert "No actionable work found" in comment

        # Should NOT request review or update column
        mock_client.request_review.assert_not_called()
        mock_client.update_item_status.assert_not_called()

    async def test_completed_no_structured_output_generic_comment(self):
        ref = _make_ref()
        trigger = _make_trigger(actions={"add_comment": True})
        session = AsyncMock()

        with patch("external_status_updater.GitHubClient") as MockClient:
            mock_client = AsyncMock()
            MockClient.from_credentials = AsyncMock(return_value=mock_client)

            await _dispatch_github(
                ref, trigger, trigger.actions,
                {"id": str(ref.task_id), "status": "completed", "output": "plain text"},
                "completed", "plain text", session,
            )

        mock_client.add_comment.assert_called_once()
        comment = mock_client.add_comment.call_args[0][1]
        assert "completed" in comment.lower()

    async def test_failed_with_add_comment(self):
        ref = _make_ref()
        trigger = _make_trigger(actions={"add_comment": True})
        session = AsyncMock()

        with patch("external_status_updater.GitHubClient") as MockClient:
            mock_client = AsyncMock()
            MockClient.from_credentials = AsyncMock(return_value=mock_client)

            await _dispatch_github(
                ref, trigger, trigger.actions,
                {"id": str(ref.task_id), "status": "failed", "output": "Exit code 1"},
                "failed", "Exit code 1", session,
            )

        mock_client.add_comment.assert_called_once()
        comment = mock_client.add_comment.call_args[0][1]
        assert "failed" in comment.lower()
        assert "Exit code 1" in comment

    async def test_action_errors_stored_in_metadata(self):
        ref = _make_ref()
        ref.metadata_ = dict(ref.metadata_)  # Make it a real dict for mutation
        trigger = _make_trigger(actions={
            "column_on_running": "In Progress",
            "column_options": {"In Progress": "opt_inprogress"},
            "project_field_id": "PVTSSF_field1",
        })
        session = AsyncMock()

        with patch("external_status_updater.GitHubClient") as MockClient:
            mock_client = AsyncMock()
            mock_client.update_item_status = AsyncMock(side_effect=Exception("API down"))
            MockClient.from_credentials = AsyncMock(return_value=mock_client)

            await _dispatch_github(
                ref, trigger, trigger.actions,
                {"id": str(ref.task_id), "status": "running"},
                "running", "", session,
            )

        assert "action_errors" in ref.metadata_
        assert any("column_on_running" in e for e in ref.metadata_["action_errors"])
        session.commit.assert_called_once()


class TestParseStructuredOutput:
    def test_valid_json_block(self):
        output = 'Text\n```json\n{"key": "value"}\n```\nMore text'
        result = _parse_structured_output(output)
        assert result == {"key": "value"}

    def test_no_json_block(self):
        assert _parse_structured_output("plain text output") is None

    def test_invalid_json(self):
        output = '```json\n{invalid}\n```'
        assert _parse_structured_output(output) is None

    def test_empty_output(self):
        assert _parse_structured_output("") is None
