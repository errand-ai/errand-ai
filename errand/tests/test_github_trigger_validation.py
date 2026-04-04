"""Tests for GitHub-specific webhook trigger validation."""

import pytest

from webhook_trigger_routes import (
    _validate_github_actions,
    _validate_github_filters,
)


@pytest.fixture(autouse=True)
def _ensure_encryption_key(monkeypatch):
    monkeypatch.setenv("CREDENTIAL_ENCRYPTION_KEY", "QqXQtnJMYRkG519FlL64LIGn3R_DvpZfeGgrWcHJV_w=")


def _expect_422(func, *args, match=None):
    """Call func and assert it raises HTTPException 422."""
    from fastapi import HTTPException
    with pytest.raises(HTTPException) as exc_info:
        func(*args)
    assert exc_info.value.status_code == 422
    if match:
        assert match in exc_info.value.detail
    return exc_info.value


class TestValidateGitHubFilters:
    def test_valid_filters(self):
        _validate_github_filters({
            "project_node_id": "PVT_abc123",
            "trigger_column": "Todo",
        })

    def test_valid_filters_with_content_types(self):
        _validate_github_filters({
            "project_node_id": "PVT_abc123",
            "trigger_column": "Todo",
            "content_types": ["Issue", "PullRequest"],
        })

    def test_missing_project_node_id(self):
        _expect_422(_validate_github_filters, {"trigger_column": "Todo"}, match="project_node_id")

    def test_missing_trigger_column(self):
        _expect_422(_validate_github_filters, {"project_node_id": "PVT_abc"}, match="trigger_column")

    def test_unknown_filter_key(self):
        _expect_422(
            _validate_github_filters,
            {"project_node_id": "PVT_abc", "trigger_column": "Todo", "bad_key": "x"},
            match="bad_key",
        )

    def test_project_node_id_must_be_string(self):
        _expect_422(
            _validate_github_filters,
            {"project_node_id": 123, "trigger_column": "Todo"},
            match="project_node_id",
        )

    def test_trigger_column_must_be_string(self):
        _expect_422(
            _validate_github_filters,
            {"project_node_id": "PVT_abc", "trigger_column": 42},
            match="trigger_column",
        )

    def test_invalid_content_type(self):
        _expect_422(
            _validate_github_filters,
            {"project_node_id": "PVT_abc", "trigger_column": "Todo", "content_types": ["BadType"]},
            match="BadType",
        )

    def test_content_types_must_be_list(self):
        _expect_422(
            _validate_github_filters,
            {"project_node_id": "PVT_abc", "trigger_column": "Todo", "content_types": "Issue"},
            match="content_types",
        )


class TestValidateGitHubActions:
    def test_valid_actions(self):
        _validate_github_actions({
            "add_comment": True,
            "comment_output": False,
            "column_on_running": "In Progress",
            "column_on_complete": "Done",
        })

    def test_empty_actions(self):
        _validate_github_actions({})

    def test_unknown_action_key(self):
        _expect_422(_validate_github_actions, {"send_email": True}, match="send_email")

    def test_add_comment_must_be_bool(self):
        _expect_422(_validate_github_actions, {"add_comment": "yes"}, match="add_comment")

    def test_comment_output_must_be_bool(self):
        _expect_422(_validate_github_actions, {"comment_output": "yes"}, match="comment_output")

    def test_copilot_review_must_be_bool(self):
        _expect_422(_validate_github_actions, {"copilot_review": "true"}, match="copilot_review")

    def test_column_on_running_must_be_str(self):
        _expect_422(_validate_github_actions, {"column_on_running": 123}, match="column_on_running")

    def test_column_on_complete_must_be_str(self):
        _expect_422(_validate_github_actions, {"column_on_complete": True}, match="column_on_complete")

    def test_review_profile_id_must_be_valid_uuid(self):
        _expect_422(_validate_github_actions, {"review_profile_id": "not-a-uuid"}, match="review_profile_id")

    def test_review_profile_id_valid_uuid(self):
        _validate_github_actions({"review_profile_id": "12345678-1234-1234-1234-123456789abc"})

    def test_column_options_must_be_dict(self):
        _expect_422(_validate_github_actions, {"column_options": ["a", "b"]}, match="column_options")

    def test_project_field_id_must_be_str(self):
        _expect_422(_validate_github_actions, {"project_field_id": 123}, match="project_field_id")

    def test_column_name_not_in_column_options(self):
        _expect_422(
            _validate_github_actions,
            {
                "column_on_running": "In Progress",
                "column_options": {"Todo": "opt1", "Done": "opt2"},
            },
            match="column_on_running",
        )

    def test_column_name_in_column_options(self):
        _validate_github_actions({
            "column_on_running": "In Progress",
            "column_on_complete": "Done",
            "column_options": {"Todo": "opt1", "In Progress": "opt2", "Done": "opt3"},
        })


@pytest.mark.asyncio
class TestGitHubTriggerRoutes:
    async def test_create_github_trigger_valid(self, admin_client):
        resp = await admin_client.post("/api/webhook-triggers", json={
            "name": "GitHub Project",
            "source": "github",
            "filters": {"project_node_id": "PVT_abc", "trigger_column": "Todo"},
            "actions": {
                "add_comment": True,
                "column_on_complete": "Done",
                "project_field_id": "PVTSSF_abc",
                "column_options": {"Done": "opt_done", "Todo": "opt_todo"},
            },
        })
        assert resp.status_code == 201
        data = resp.json()
        assert data["source"] == "github"
        assert data["filters"]["project_node_id"] == "PVT_abc"

    async def test_create_github_trigger_missing_required_filter(self, admin_client):
        resp = await admin_client.post("/api/webhook-triggers", json={
            "name": "Missing Filter",
            "source": "github",
            "filters": {"trigger_column": "Todo"},
        })
        assert resp.status_code == 422
        assert "project_node_id" in resp.json()["detail"]

    async def test_create_github_trigger_unknown_filter(self, admin_client):
        resp = await admin_client.post("/api/webhook-triggers", json={
            "name": "Unknown Filter",
            "source": "github",
            "filters": {"project_node_id": "PVT_abc", "trigger_column": "Todo", "priority": "high"},
        })
        assert resp.status_code == 422
        assert "priority" in resp.json()["detail"]

    async def test_create_github_trigger_invalid_content_type(self, admin_client):
        resp = await admin_client.post("/api/webhook-triggers", json={
            "name": "Bad Content Type",
            "source": "github",
            "filters": {
                "project_node_id": "PVT_abc",
                "trigger_column": "Todo",
                "content_types": ["BadType"],
            },
        })
        assert resp.status_code == 422
        assert "BadType" in resp.json()["detail"]

    async def test_create_github_trigger_unknown_action(self, admin_client):
        resp = await admin_client.post("/api/webhook-triggers", json={
            "name": "Unknown Action",
            "source": "github",
            "filters": {"project_node_id": "PVT_abc", "trigger_column": "Todo"},
            "actions": {"assign_to": "user"},
        })
        assert resp.status_code == 422
        assert "assign_to" in resp.json()["detail"]

    async def test_create_github_trigger_wrong_action_type(self, admin_client):
        resp = await admin_client.post("/api/webhook-triggers", json={
            "name": "Wrong Type",
            "source": "github",
            "filters": {"project_node_id": "PVT_abc", "trigger_column": "Todo"},
            "actions": {"add_comment": "yes"},
        })
        assert resp.status_code == 422
        assert "add_comment" in resp.json()["detail"]

    async def test_create_github_trigger_column_not_in_options(self, admin_client):
        resp = await admin_client.post("/api/webhook-triggers", json={
            "name": "Bad Column",
            "source": "github",
            "filters": {"project_node_id": "PVT_abc", "trigger_column": "Todo"},
            "actions": {
                "column_on_running": "In Progress",
                "column_options": {"Todo": "opt1", "Done": "opt2"},
            },
        })
        assert resp.status_code == 422
        assert "column_on_running" in resp.json()["detail"]

    async def test_jira_trigger_still_uses_jira_validation(self, admin_client):
        """Jira triggers should use the original validation, not GitHub's."""
        resp = await admin_client.post("/api/webhook-triggers", json={
            "name": "Jira Still Works",
            "source": "jira",
            "filters": {"event_types": ["issue_created"]},
            "actions": {"add_comment": True},
        })
        assert resp.status_code == 201

    async def test_update_github_trigger_validates(self, admin_client):
        create = await admin_client.post("/api/webhook-triggers", json={
            "name": "Update Me",
            "source": "github",
            "filters": {"project_node_id": "PVT_abc", "trigger_column": "Todo"},
        })
        tid = create.json()["id"]
        resp = await admin_client.put(f"/api/webhook-triggers/{tid}", json={
            "filters": {"bad_key": "x"},
        })
        assert resp.status_code == 422
