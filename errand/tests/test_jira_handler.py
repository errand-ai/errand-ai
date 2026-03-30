"""Tests for Jira webhook handler."""

import json
import os
import uuid

import pytest


@pytest.fixture(autouse=True)
def _ensure_encryption_key(monkeypatch):
    monkeypatch.setenv("CREDENTIAL_ENCRYPTION_KEY", "QqXQtnJMYRkG519FlL64LIGn3R_DvpZfeGgrWcHJV_w=")

from unittest.mock import MagicMock
from platforms.jira.handler import parse_jira_payload, evaluate_filters, _label_just_added


def _make_payload(
    event="jira:issue_created",
    issue_key="PROJ-123",
    summary="Fix login",
    issue_type="Bug",
    labels=None,
    project_key="PROJ",
    parent_key=None,
    changelog=None,
):
    payload = {
        "webhookEvent": event,
        "issue": {
            "key": issue_key,
            "self": f"https://jira.example.com/rest/api/3/issue/{issue_key}",
            "fields": {
                "summary": summary,
                "description": "Some description",
                "issuetype": {"name": issue_type},
                "labels": labels or [],
                "project": {"key": project_key},
                "reporter": {"displayName": "Jane Doe"},
                "priority": {"name": "High"},
            },
        },
    }
    if parent_key:
        payload["issue"]["fields"]["parent"] = {"key": parent_key}
    if changelog:
        payload["changelog"] = changelog
    return json.dumps(payload).encode()


def _make_trigger(
    filters=None,
    actions=None,
    source="jira",
    enabled=True,
):
    trigger = MagicMock()
    trigger.id = uuid.uuid4()
    trigger.source = source
    trigger.enabled = enabled
    trigger.filters = filters or {}
    trigger.actions = actions or {}
    trigger.profile_id = None
    trigger.webhook_secret = None
    return trigger


class TestParseJiraPayload:
    def test_valid_payload(self):
        body = _make_payload()
        result = parse_jira_payload(body)
        assert result is not None
        assert result["event"] == "jira:issue_created"
        assert result["issue_key"] == "PROJ-123"
        assert result["summary"] == "Fix login"
        assert result["issue_type"] == "Bug"
        assert result["project_key"] == "PROJ"

    def test_missing_issue(self):
        body = json.dumps({"webhookEvent": "jira:issue_created"}).encode()
        assert parse_jira_payload(body) is None

    def test_missing_event(self):
        body = json.dumps({"issue": {"key": "X-1", "fields": {}}}).encode()
        assert parse_jira_payload(body) is None

    def test_invalid_json(self):
        assert parse_jira_payload(b"not json") is None

    def test_parent_key_extracted(self):
        body = _make_payload(parent_key="PROJ-100")
        result = parse_jira_payload(body)
        assert result["parent_key"] == "PROJ-100"


class TestEvaluateFilters:
    def test_empty_filters_match_all(self):
        trigger = _make_trigger(filters={})
        payload = parse_jira_payload(_make_payload())
        assert evaluate_filters(trigger, payload) is True

    def test_event_type_matches(self):
        trigger = _make_trigger(filters={"event_types": ["jira:issue_created"]})
        payload = parse_jira_payload(_make_payload(event="jira:issue_created"))
        assert evaluate_filters(trigger, payload) is True

    def test_event_type_no_match(self):
        trigger = _make_trigger(filters={"event_types": ["jira:issue_created"]})
        payload = parse_jira_payload(_make_payload(event="jira:issue_updated"))
        assert evaluate_filters(trigger, payload) is False

    def test_issue_type_matches_case_insensitive(self):
        trigger = _make_trigger(filters={"issue_types": ["Bug"]})
        payload = parse_jira_payload(_make_payload(issue_type="bug"))
        assert evaluate_filters(trigger, payload) is True

    def test_issue_type_no_match(self):
        trigger = _make_trigger(filters={"issue_types": ["Task"]})
        payload = parse_jira_payload(_make_payload(issue_type="Bug"))
        assert evaluate_filters(trigger, payload) is False

    def test_labels_match_on_create(self):
        trigger = _make_trigger(filters={"labels": ["errand"]})
        payload = parse_jira_payload(_make_payload(labels=["errand", "frontend"]))
        assert evaluate_filters(trigger, payload) is True

    def test_labels_no_match_on_create(self):
        trigger = _make_trigger(filters={"labels": ["errand"]})
        payload = parse_jira_payload(_make_payload(labels=["backend"]))
        assert evaluate_filters(trigger, payload) is False

    def test_labels_match_on_update_changelog(self):
        changelog = {
            "items": [{"field": "labels", "fromString": "", "toString": "errand"}]
        }
        trigger = _make_trigger(filters={"labels": ["errand"]})
        payload = parse_jira_payload(_make_payload(
            event="jira:issue_updated",
            labels=["errand"],
            changelog=changelog,
        ))
        assert evaluate_filters(trigger, payload) is True

    def test_labels_no_match_on_update_already_existed(self):
        changelog = {
            "items": [{"field": "summary", "fromString": "old", "toString": "new"}]
        }
        trigger = _make_trigger(filters={"labels": ["errand"]})
        payload = parse_jira_payload(_make_payload(
            event="jira:issue_updated",
            labels=["errand"],
            changelog=changelog,
        ))
        assert evaluate_filters(trigger, payload) is False

    def test_projects_match(self):
        trigger = _make_trigger(filters={"projects": ["PROJ"]})
        payload = parse_jira_payload(_make_payload(project_key="PROJ"))
        assert evaluate_filters(trigger, payload) is True

    def test_projects_no_match(self):
        trigger = _make_trigger(filters={"projects": ["OTHER"]})
        payload = parse_jira_payload(_make_payload(project_key="PROJ"))
        assert evaluate_filters(trigger, payload) is False

    def test_combined_filters(self):
        trigger = _make_trigger(filters={
            "event_types": ["jira:issue_created"],
            "issue_types": ["Bug"],
            "projects": ["PROJ"],
        })
        payload = parse_jira_payload(_make_payload(
            event="jira:issue_created",
            issue_type="Bug",
            project_key="PROJ",
        ))
        assert evaluate_filters(trigger, payload) is True

    def test_combined_filters_one_fails(self):
        trigger = _make_trigger(filters={
            "event_types": ["jira:issue_created"],
            "issue_types": ["Bug"],
            "projects": ["OTHER"],
        })
        payload = parse_jira_payload(_make_payload(
            event="jira:issue_created",
            issue_type="Bug",
            project_key="PROJ",
        ))
        assert evaluate_filters(trigger, payload) is False
