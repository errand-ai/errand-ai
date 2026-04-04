"""Tests for GitHub webhook handler."""

import json
import uuid

import pytest

from unittest.mock import MagicMock
from platforms.github.handler import parse_github_payload, evaluate_filters


@pytest.fixture(autouse=True)
def _ensure_encryption_key(monkeypatch):
    monkeypatch.setenv("CREDENTIAL_ENCRYPTION_KEY", "QqXQtnJMYRkG519FlL64LIGn3R_DvpZfeGgrWcHJV_w=")


def _make_payload(
    action="edited",
    node_id="PVTI_node123",
    project_node_id="PVT_proj456",
    content_node_id="I_issue789",
    content_type="Issue",
    field_name="Status",
    from_name="Todo",
    to_name="In Progress",
    org_login="my-org",
    sender_login="octocat",
):
    payload = {
        "action": action,
        "projects_v2_item": {
            "node_id": node_id,
            "project_node_id": project_node_id,
            "content_node_id": content_node_id,
            "content_type": content_type,
        },
        "changes": {
            "field_value": {
                "field_name": field_name,
                "from": {"name": from_name},
                "to": {"name": to_name},
            },
        },
        "organization": {"login": org_login},
        "sender": {"login": sender_login},
    }
    return json.dumps(payload).encode()


def _make_trigger(
    filters=None,
    source="github",
    enabled=True,
):
    trigger = MagicMock()
    trigger.id = uuid.uuid4()
    trigger.source = source
    trigger.enabled = enabled
    trigger.filters = filters or {}
    trigger.profile_id = None
    trigger.webhook_secret = None
    return trigger


class TestParseGitHubPayload:
    def test_valid_payload(self):
        body = _make_payload()
        result = parse_github_payload(body)
        assert result is not None
        assert result["action"] == "edited"
        assert result["item_node_id"] == "PVTI_node123"
        assert result["project_node_id"] == "PVT_proj456"
        assert result["content_node_id"] == "I_issue789"
        assert result["content_type"] == "Issue"
        assert result["field_name"] == "Status"
        assert result["from_name"] == "Todo"
        assert result["to_name"] == "In Progress"
        assert result["organization_login"] == "my-org"
        assert result["sender_login"] == "octocat"

    def test_missing_action(self):
        data = {
            "projects_v2_item": {"node_id": "x", "project_node_id": "y"},
        }
        assert parse_github_payload(json.dumps(data).encode()) is None

    def test_missing_projects_v2_item(self):
        data = {"action": "edited"}
        assert parse_github_payload(json.dumps(data).encode()) is None

    def test_invalid_json(self):
        assert parse_github_payload(b"not json") is None

    def test_missing_changes_returns_empty_strings(self):
        data = {
            "action": "created",
            "projects_v2_item": {
                "node_id": "x",
                "project_node_id": "y",
                "content_node_id": "z",
                "content_type": "Issue",
            },
        }
        result = parse_github_payload(json.dumps(data).encode())
        assert result is not None
        assert result["field_name"] == ""
        assert result["from_name"] == ""
        assert result["to_name"] == ""

    def test_missing_organization_and_sender(self):
        data = {
            "action": "edited",
            "projects_v2_item": {
                "node_id": "x",
                "project_node_id": "y",
                "content_node_id": "z",
                "content_type": "Issue",
            },
        }
        result = parse_github_payload(json.dumps(data).encode())
        assert result is not None
        assert result["organization_login"] == ""
        assert result["sender_login"] == ""


class TestEvaluateFilters:
    def _default_filters(self, **overrides):
        base = {
            "project_node_id": "PVT_proj456",
            "trigger_column": "In Progress",
        }
        base.update(overrides)
        return base

    def test_matching_filters(self):
        trigger = _make_trigger(filters=self._default_filters())
        payload = parse_github_payload(_make_payload())
        assert evaluate_filters(trigger, payload) is True

    def test_non_edited_action(self):
        trigger = _make_trigger(filters=self._default_filters())
        payload = parse_github_payload(_make_payload(action="created"))
        assert evaluate_filters(trigger, payload) is False

    def test_non_status_field(self):
        trigger = _make_trigger(filters=self._default_filters())
        payload = parse_github_payload(_make_payload(field_name="Priority"))
        assert evaluate_filters(trigger, payload) is False

    def test_project_node_id_no_match(self):
        trigger = _make_trigger(filters=self._default_filters(project_node_id="PVT_other"))
        payload = parse_github_payload(_make_payload())
        assert evaluate_filters(trigger, payload) is False

    def test_trigger_column_no_match(self):
        trigger = _make_trigger(filters=self._default_filters(trigger_column="Done"))
        payload = parse_github_payload(_make_payload())
        assert evaluate_filters(trigger, payload) is False

    def test_trigger_column_case_insensitive(self):
        trigger = _make_trigger(filters=self._default_filters(trigger_column="in progress"))
        payload = parse_github_payload(_make_payload(to_name="In Progress"))
        assert evaluate_filters(trigger, payload) is True

    def test_content_type_match(self):
        trigger = _make_trigger(filters=self._default_filters(
            content_types=["Issue", "PullRequest"]
        ))
        payload = parse_github_payload(_make_payload(content_type="PullRequest"))
        assert evaluate_filters(trigger, payload) is True

    def test_content_type_no_match(self):
        trigger = _make_trigger(filters=self._default_filters(
            content_types=["Issue"]
        ))
        payload = parse_github_payload(_make_payload(content_type="DraftIssue"))
        assert evaluate_filters(trigger, payload) is False

    def test_default_content_types_allows_issue(self):
        """When content_types is not in filters, default is ["Issue"]."""
        trigger = _make_trigger(filters=self._default_filters())
        payload = parse_github_payload(_make_payload(content_type="Issue"))
        assert evaluate_filters(trigger, payload) is True

    def test_default_content_types_rejects_pull_request(self):
        """When content_types is not in filters, PullRequest is not allowed."""
        trigger = _make_trigger(filters=self._default_filters())
        payload = parse_github_payload(_make_payload(content_type="PullRequest"))
        assert evaluate_filters(trigger, payload) is False
