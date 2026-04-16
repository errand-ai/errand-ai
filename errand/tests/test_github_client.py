"""Tests for GitHubClient."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from platforms.github.client import GitHubClient, GitHubClientError


@pytest.fixture(autouse=True)
def _ensure_encryption_key(monkeypatch):
    monkeypatch.setenv("CREDENTIAL_ENCRYPTION_KEY", "QqXQtnJMYRkG519FlL64LIGn3R_DvpZfeGgrWcHJV_w=")


def _mock_httpx_response(status_code=200, json_data=None, text=""):
    resp = MagicMock()
    resp.status_code = status_code
    resp.text = text
    resp.is_success = 200 <= status_code < 300
    resp.json.return_value = json_data or {}
    return resp


def _patch_httpx(response):
    """Patch httpx.AsyncClient so post/request return the given response."""
    mock_client = AsyncMock()
    mock_client.post.return_value = response
    mock_client.request.return_value = response

    patcher = patch("platforms.github.client.httpx.AsyncClient")
    mock_cls = patcher.start()
    mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
    mock_cls.return_value.__aexit__ = AsyncMock(return_value=None)
    return patcher, mock_client


# ---------------------------------------------------------------------------
# _graphql
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
class TestGraphQL:
    async def test_success(self):
        resp = _mock_httpx_response(json_data={"data": {"viewer": {"login": "octocat"}}})
        patcher, mock_client = _patch_httpx(resp)
        try:
            client = GitHubClient(token="ghp_test")
            data = await client._graphql("query { viewer { login } }")
            assert data == {"viewer": {"login": "octocat"}}
            mock_client.post.assert_called_once()
        finally:
            patcher.stop()

    async def test_graphql_errors(self):
        resp = _mock_httpx_response(json_data={
            "data": None,
            "errors": [{"message": "Field 'x' not found"}],
        })
        patcher, _ = _patch_httpx(resp)
        try:
            client = GitHubClient(token="ghp_test")
            with pytest.raises(GitHubClientError, match="Field 'x' not found"):
                await client._graphql("query { x }")
        finally:
            patcher.stop()

    async def test_http_401(self):
        resp = _mock_httpx_response(status_code=401, text="Bad credentials")
        patcher, _ = _patch_httpx(resp)
        try:
            client = GitHubClient(token="ghp_expired")
            with pytest.raises(GitHubClientError, match="401"):
                await client._graphql("query { viewer { login } }")
        finally:
            patcher.stop()

    async def test_http_500(self):
        resp = _mock_httpx_response(status_code=500, text="Internal Server Error")
        patcher, _ = _patch_httpx(resp)
        try:
            client = GitHubClient(token="ghp_test")
            with pytest.raises(GitHubClientError, match="500"):
                await client._graphql("query { viewer { login } }")
        finally:
            patcher.stop()


# ---------------------------------------------------------------------------
# introspect_project
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
class TestIntrospectProject:
    async def test_success(self):
        resp = _mock_httpx_response(json_data={"data": {
            "organization": {
                "projectV2": {
                    "id": "PVT_abc",
                    "title": "My Project",
                    "fields": {"nodes": [
                        {"id": "FLD_1", "name": "Title"},
                        {
                            "id": "FLD_2",
                            "name": "Status",
                            "options": [
                                {"id": "OPT_a", "name": "Todo"},
                                {"id": "OPT_b", "name": "In Progress"},
                            ],
                        },
                    ]},
                }
            }
        }})
        patcher, _ = _patch_httpx(resp)
        try:
            client = GitHubClient(token="ghp_test")
            result = await client.introspect_project("my-org", 5)

            assert result["project_node_id"] == "PVT_abc"
            assert result["title"] == "My Project"
            assert len(result["fields"]) == 2

            status_field = result["fields"][1]
            assert status_field["type"] == "SingleSelectField"
            assert len(status_field["options"]) == 2
            assert status_field["options"][0]["name"] == "Todo"
        finally:
            patcher.stop()

    async def test_project_not_found(self):
        resp = _mock_httpx_response(json_data={"data": {
            "organization": {"projectV2": None}
        }})
        patcher, _ = _patch_httpx(resp)
        try:
            client = GitHubClient(token="ghp_test")
            with pytest.raises(GitHubClientError, match="Project #99 not found"):
                await client.introspect_project("my-org", 99)
        finally:
            patcher.stop()

    async def test_org_not_accessible(self):
        resp = _mock_httpx_response(json_data={"data": {"organization": None}})
        patcher, _ = _patch_httpx(resp)
        try:
            client = GitHubClient(token="ghp_test")
            with pytest.raises(GitHubClientError, match="not found or not accessible"):
                await client.introspect_project("secret-org", 1)
        finally:
            patcher.stop()


# ---------------------------------------------------------------------------
# resolve_issue
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
class TestResolveIssue:
    async def test_success(self):
        resp = _mock_httpx_response(json_data={"data": {"node": {
            "__typename": "Issue",
            "number": 42,
            "title": "Bug report",
            "body": "Something is broken",
            "state": "OPEN",
            "url": "https://github.com/my-org/my-repo/issues/42",
            "repository": {
                "name": "my-repo",
                "owner": {"login": "my-org"},
            },
            "labels": {"nodes": [{"name": "bug"}, {"name": "urgent"}]},
            "assignees": {"nodes": [{"login": "alice"}, {"login": "bob"}]},
        }}})
        patcher, _ = _patch_httpx(resp)
        try:
            client = GitHubClient(token="ghp_test")
            result = await client.resolve_issue("I_abc123")

            assert result["number"] == 42
            assert result["title"] == "Bug report"
            assert result["body"] == "Something is broken"
            assert result["state"] == "OPEN"
            assert result["repo_owner"] == "my-org"
            assert result["repo_name"] == "my-repo"
            assert result["labels"] == ["bug", "urgent"]
            assert result["assignees"] == ["alice", "bob"]
        finally:
            patcher.stop()

    async def test_draft_issue_rejected(self):
        resp = _mock_httpx_response(json_data={"data": {"node": {
            "__typename": "DraftIssue",
            "title": "Draft thing",
        }}})
        patcher, _ = _patch_httpx(resp)
        try:
            client = GitHubClient(token="ghp_test")
            with pytest.raises(GitHubClientError, match="DraftIssue"):
                await client.resolve_issue("DI_xyz")
        finally:
            patcher.stop()

    async def test_non_issue_node(self):
        resp = _mock_httpx_response(json_data={"data": {"node": {
            "__typename": "PullRequest",
        }}})
        patcher, _ = _patch_httpx(resp)
        try:
            client = GitHubClient(token="ghp_test")
            with pytest.raises(GitHubClientError, match="PullRequest, not an Issue"):
                await client.resolve_issue("PR_abc")
        finally:
            patcher.stop()


# ---------------------------------------------------------------------------
# find_project_item
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
class TestFindProjectItem:
    async def test_item_found(self):
        resp = _mock_httpx_response(json_data={"data": {"node": {
            "projectItems": {"nodes": [
                {
                    "id": "PVTI_item1",
                    "project": {"id": "PVT_other"},
                    "fieldValues": {"nodes": []},
                },
                {
                    "id": "PVTI_item2",
                    "project": {"id": "PVT_target"},
                    "fieldValues": {"nodes": [
                        {
                            "field": {"name": "Status"},
                            "name": "In Progress",
                            "optionId": "OPT_ip",
                        },
                    ]},
                },
            ]},
        }}})
        patcher, _ = _patch_httpx(resp)
        try:
            client = GitHubClient(token="ghp_test")
            result = await client.find_project_item("I_abc", "PVT_target")

            assert result is not None
            assert result["item_id"] == "PVTI_item2"
            assert result["status_name"] == "In Progress"
            assert result["status_option_id"] == "OPT_ip"
        finally:
            patcher.stop()

    async def test_item_not_in_project(self):
        resp = _mock_httpx_response(json_data={"data": {"node": {
            "projectItems": {"nodes": [
                {
                    "id": "PVTI_item1",
                    "project": {"id": "PVT_other"},
                    "fieldValues": {"nodes": []},
                },
            ]},
        }}})
        patcher, _ = _patch_httpx(resp)
        try:
            client = GitHubClient(token="ghp_test")
            result = await client.find_project_item("I_abc", "PVT_missing")
            assert result is None
        finally:
            patcher.stop()


# ---------------------------------------------------------------------------
# update_item_status
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
class TestUpdateItemStatus:
    async def test_success(self):
        resp = _mock_httpx_response(json_data={"data": {
            "updateProjectV2ItemFieldValue": {"projectV2Item": {"id": "PVTI_item1"}}
        }})
        patcher, mock_client = _patch_httpx(resp)
        try:
            client = GitHubClient(token="ghp_test")
            await client.update_item_status("PVT_abc", "PVTI_item1", "FLD_1", "OPT_a")

            call_kwargs = mock_client.post.call_args
            payload = call_kwargs.kwargs.get("json") or call_kwargs[1].get("json")
            assert "variables" in payload
            assert payload["variables"]["input"]["projectId"] == "PVT_abc"
        finally:
            patcher.stop()

    async def test_error(self):
        resp = _mock_httpx_response(json_data={
            "errors": [{"message": "Could not resolve to a ProjectV2Item"}],
        })
        patcher, _ = _patch_httpx(resp)
        try:
            client = GitHubClient(token="ghp_test")
            with pytest.raises(GitHubClientError, match="Could not resolve"):
                await client.update_item_status("PVT_x", "PVTI_x", "FLD_x", "OPT_x")
        finally:
            patcher.stop()


# ---------------------------------------------------------------------------
# add_comment
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
class TestAddComment:
    async def test_success(self):
        resp = _mock_httpx_response(json_data={"data": {
            "addComment": {
                "commentEdge": {
                    "node": {"url": "https://github.com/my-org/my-repo/issues/42#issuecomment-123"}
                }
            }
        }})
        patcher, _ = _patch_httpx(resp)
        try:
            client = GitHubClient(token="ghp_test")
            url = await client.add_comment("I_abc", "Task completed")
            assert url == "https://github.com/my-org/my-repo/issues/42#issuecomment-123"
        finally:
            patcher.stop()


# ---------------------------------------------------------------------------
# request_review
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
class TestRequestReview:
    async def test_success(self):
        resp = _mock_httpx_response(status_code=201)
        patcher, mock_client = _patch_httpx(resp)
        try:
            client = GitHubClient(token="ghp_test")
            await client.request_review("my-org", "my-repo", 10, ["alice"])
            mock_client.request.assert_called_once()
        finally:
            patcher.stop()

    async def test_422_warning_no_exception(self):
        resp = _mock_httpx_response(status_code=422, text="Validation Failed")
        patcher, _ = _patch_httpx(resp)
        try:
            client = GitHubClient(token="ghp_test")
            # Should not raise — 422 is logged as warning
            await client.request_review("my-org", "my-repo", 10, ["bot-user"])
        finally:
            patcher.stop()

    async def test_other_error_raises(self):
        resp = _mock_httpx_response(status_code=500, text="Server Error")
        patcher, _ = _patch_httpx(resp)
        try:
            client = GitHubClient(token="ghp_test")
            with pytest.raises(GitHubClientError, match="500"):
                await client.request_review("my-org", "my-repo", 10, ["alice"])
        finally:
            patcher.stop()


# ---------------------------------------------------------------------------
# from_credentials
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
class TestFromCredentials:
    async def test_pat_mode(self):
        session = AsyncMock()
        with patch("platforms.github.client.load_credentials", new_callable=AsyncMock) as mock_load:
            mock_load.return_value = {
                "auth_mode": "pat",
                "personal_access_token": "ghp_my_token",
            }
            client = await GitHubClient.from_credentials(session)
            assert client._token == "ghp_my_token"

    async def test_app_mode(self):
        session = AsyncMock()
        with patch("platforms.github.client.load_credentials", new_callable=AsyncMock) as mock_load, \
             patch("platforms.github.client.mint_installation_token") as mock_mint:
            mock_load.return_value = {
                "auth_mode": "app",
                "app_id": "123",
                "private_key": "fake-key",
                "installation_id": "456",
            }
            mock_mint.return_value = "ghs_ephemeral"
            client = await GitHubClient.from_credentials(session)
            assert client._token == "ghs_ephemeral"
            mock_mint.assert_called_once_with(
                app_id="123", private_key="fake-key", installation_id="456",
            )

    async def test_no_credentials(self):
        session = AsyncMock()
        with patch("platforms.github.client.load_credentials", new_callable=AsyncMock) as mock_load:
            mock_load.return_value = None
            with pytest.raises(GitHubClientError, match="No GitHub credentials"):
                await GitHubClient.from_credentials(session)
