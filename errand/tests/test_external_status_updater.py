"""Tests for ExternalStatusUpdater."""

import os
import uuid

import pytest


@pytest.fixture(autouse=True)
def _ensure_encryption_key(monkeypatch):
    monkeypatch.setenv("CREDENTIAL_ENCRYPTION_KEY", "QqXQtnJMYRkG519FlL64LIGn3R_DvpZfeGgrWcHJV_w=")

from unittest.mock import AsyncMock, MagicMock, patch

from external_status_updater import _process_task_event, _dispatch_jira


def _make_ref(external_id="PROJ-123", source="jira", trigger_id=None):
    ref = MagicMock()
    ref.id = uuid.uuid4()
    ref.task_id = uuid.uuid4()
    ref.trigger_id = trigger_id or uuid.uuid4()
    ref.source = source
    ref.external_id = external_id
    return ref


def _make_trigger(actions=None):
    trigger = MagicMock()
    trigger.id = uuid.uuid4()
    trigger.actions = actions or {}
    return trigger


@pytest.mark.asyncio
class TestDispatchJira:
    async def test_running_with_comment(self):
        ref = _make_ref()
        trigger = _make_trigger(actions={"add_comment": True})
        session = AsyncMock()

        with patch("external_status_updater.JiraClient") as MockClient:
            mock_jira = AsyncMock()
            MockClient.from_credentials = AsyncMock(return_value=mock_jira)

            await _dispatch_jira(
                ref, trigger, trigger.actions,
                {"id": str(ref.task_id), "status": "running"},
                "running", "", session,
            )

        mock_jira.add_comment.assert_called_once()
        assert "started" in mock_jira.add_comment.call_args[0][1].lower()

    async def test_running_with_assign(self):
        ref = _make_ref()
        trigger = _make_trigger(actions={"assign_to": "bot"})
        session = AsyncMock()

        with patch("external_status_updater.JiraClient") as MockClient:
            mock_jira = AsyncMock()
            MockClient.from_credentials = AsyncMock(return_value=mock_jira)

            await _dispatch_jira(
                ref, trigger, trigger.actions,
                {"id": str(ref.task_id), "status": "running"},
                "running", "", session,
            )

        mock_jira.assign_to_service_account.assert_called_once()

    async def test_completed_with_comment_and_transition(self):
        ref = _make_ref()
        trigger = _make_trigger(actions={
            "add_comment": True,
            "comment_output": True,
            "transition_on_complete": "Done",
        })
        session = AsyncMock()

        with patch("external_status_updater.JiraClient") as MockClient:
            mock_jira = AsyncMock()
            MockClient.from_credentials = AsyncMock(return_value=mock_jira)

            await _dispatch_jira(
                ref, trigger, trigger.actions,
                {"id": str(ref.task_id), "status": "completed", "output": "All done!"},
                "completed", "All done!", session,
            )

        mock_jira.add_comment.assert_called_once()
        assert "All done!" in mock_jira.add_comment.call_args[0][1]
        mock_jira.transition_issue.assert_called_once_with("PROJ-123", "Done")

    async def test_failed_with_comment(self):
        ref = _make_ref()
        trigger = _make_trigger(actions={"add_comment": True})
        session = AsyncMock()

        with patch("external_status_updater.JiraClient") as MockClient:
            mock_jira = AsyncMock()
            MockClient.from_credentials = AsyncMock(return_value=mock_jira)

            await _dispatch_jira(
                ref, trigger, trigger.actions,
                {"id": str(ref.task_id), "status": "failed", "output": "Exit code 1"},
                "failed", "Exit code 1", session,
            )

        mock_jira.add_comment.assert_called_once()
        assert "failed" in mock_jira.add_comment.call_args[0][1].lower()
        assert "Exit code 1" in mock_jira.add_comment.call_args[0][1]

    async def test_no_actions_configured(self):
        ref = _make_ref()
        trigger = _make_trigger(actions={})
        session = AsyncMock()

        with patch("external_status_updater.JiraClient") as MockClient:
            mock_jira = AsyncMock()
            MockClient.from_credentials = AsyncMock(return_value=mock_jira)

            await _dispatch_jira(
                ref, trigger, trigger.actions,
                {"id": str(ref.task_id), "status": "running"},
                "running", "", session,
            )

        mock_jira.add_comment.assert_not_called()
        mock_jira.assign_to_service_account.assert_not_called()

    async def test_completed_with_add_label(self):
        ref = _make_ref()
        trigger = _make_trigger(actions={"add_label": "errand-processed"})
        session = AsyncMock()

        with patch("external_status_updater.JiraClient") as MockClient:
            mock_jira = AsyncMock()
            MockClient.from_credentials = AsyncMock(return_value=mock_jira)

            await _dispatch_jira(
                ref, trigger, trigger.actions,
                {"id": str(ref.task_id), "status": "completed"},
                "completed", "", session,
            )

        mock_jira.add_label.assert_called_once_with("PROJ-123", "errand-processed")

    async def test_action_errors_stored_in_ref_metadata(self):
        ref = _make_ref()
        ref.metadata_ = {}
        trigger = _make_trigger(actions={"add_comment": True})
        session = AsyncMock()

        with patch("external_status_updater.JiraClient") as MockClient:
            mock_jira = AsyncMock()
            mock_jira.add_comment = AsyncMock(return_value=False)  # Action fails
            MockClient.from_credentials = AsyncMock(return_value=mock_jira)

            await _dispatch_jira(
                ref, trigger, trigger.actions,
                {"id": str(ref.task_id), "status": "running"},
                "running", "", session,
            )

        assert "action_errors" in ref.metadata_
        assert len(ref.metadata_["action_errors"]) == 1
        assert "add_comment failed" in ref.metadata_["action_errors"][0]
        session.commit.assert_called_once()

    async def test_no_errors_stored_when_actions_succeed(self):
        ref = _make_ref()
        ref.metadata_ = {}
        trigger = _make_trigger(actions={"add_comment": True})
        session = AsyncMock()

        with patch("external_status_updater.JiraClient") as MockClient:
            mock_jira = AsyncMock()
            mock_jira.add_comment = AsyncMock(return_value=True)  # Action succeeds
            MockClient.from_credentials = AsyncMock(return_value=mock_jira)

            await _dispatch_jira(
                ref, trigger, trigger.actions,
                {"id": str(ref.task_id), "status": "running"},
                "running", "", session,
            )

        assert "action_errors" not in ref.metadata_
        session.commit.assert_not_called()  # No errors = no extra commit
