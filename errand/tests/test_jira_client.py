"""Tests for Jira REST API client."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from platforms.jira.client import JiraClient, JiraCredentialError, _account_id_cache


@pytest.fixture(autouse=True)
def clear_account_cache():
    _account_id_cache.clear()


def _mock_response(status_code=200, json_data=None, text=""):
    resp = MagicMock()
    resp.status_code = status_code
    resp.is_success = 200 <= status_code < 300
    resp.json.return_value = json_data or {}
    resp.text = text
    return resp


def _client():
    return JiraClient(
        cloud_id="test-cloud",
        api_token="test-token",
        service_account_email="bot@test.com",
    )


@pytest.mark.asyncio
class TestJiraClientComments:
    async def test_add_comment_success(self):
        client = _client()
        with patch.object(client, "_request", new_callable=AsyncMock) as mock:
            mock.return_value = _mock_response(201)
            result = await client.add_comment("PROJ-1", "Task completed successfully")
        assert result is True
        mock.assert_called_once()
        call_kwargs = mock.call_args
        assert "PROJ-1" in call_kwargs[0][1]

    async def test_add_comment_truncates_large_output(self):
        client = _client()
        long_text = "x" * 40_000
        with patch.object(client, "_request", new_callable=AsyncMock) as mock:
            mock.return_value = _mock_response(201)
            await client.add_comment("PROJ-1", long_text)
        body = mock.call_args[1]["json"]["body"]["content"][0]["content"][0]["text"]
        assert len(body) < 35_000
        assert "[output truncated]" in body

    async def test_add_comment_failure(self):
        client = _client()
        with patch.object(client, "_request", new_callable=AsyncMock) as mock:
            mock.return_value = _mock_response(500, text="Server error")
            result = await client.add_comment("PROJ-1", "text")
        assert result is False


@pytest.mark.asyncio
class TestJiraClientTransitions:
    async def test_transition_success(self):
        client = _client()
        transitions_resp = _mock_response(200, json_data={
            "transitions": [
                {"id": "1", "name": "In Progress"},
                {"id": "2", "name": "Done"},
            ]
        })
        transition_resp = _mock_response(204)

        with patch.object(client, "_request", new_callable=AsyncMock) as mock:
            mock.side_effect = [transitions_resp, transition_resp]
            result = await client.transition_issue("PROJ-1", "Done")
        assert result is True

    async def test_transition_case_insensitive(self):
        client = _client()
        transitions_resp = _mock_response(200, json_data={
            "transitions": [{"id": "2", "name": "Done"}]
        })
        transition_resp = _mock_response(204)

        with patch.object(client, "_request", new_callable=AsyncMock) as mock:
            mock.side_effect = [transitions_resp, transition_resp]
            result = await client.transition_issue("PROJ-1", "done")
        assert result is True

    async def test_transition_not_available(self):
        client = _client()
        transitions_resp = _mock_response(200, json_data={
            "transitions": [{"id": "1", "name": "In Progress"}]
        })

        with patch.object(client, "_request", new_callable=AsyncMock) as mock:
            mock.return_value = transitions_resp
            result = await client.transition_issue("PROJ-1", "Done")
        assert result is False


@pytest.mark.asyncio
class TestJiraClientAssignment:
    async def test_assign_success(self):
        client = _client()
        search_resp = _mock_response(200, json_data=[{"accountId": "abc123"}])
        assign_resp = _mock_response(204)

        with patch.object(client, "_request", new_callable=AsyncMock) as mock:
            mock.side_effect = [search_resp, assign_resp]
            result = await client.assign_to_service_account("PROJ-1")
        assert result is True

    async def test_assign_caches_account_id(self):
        client = _client()
        search_resp = _mock_response(200, json_data=[{"accountId": "abc123"}])
        assign_resp = _mock_response(204)

        with patch.object(client, "_request", new_callable=AsyncMock) as mock:
            mock.side_effect = [search_resp, assign_resp, assign_resp]
            await client.assign_to_service_account("PROJ-1")
            await client.assign_to_service_account("PROJ-2")
        # 3 calls: search + assign + assign (no second search)
        assert mock.call_count == 3

    async def test_assign_no_user_found(self):
        client = _client()
        search_resp = _mock_response(200, json_data=[])

        with patch.object(client, "_request", new_callable=AsyncMock) as mock:
            mock.return_value = search_resp
            result = await client.assign_to_service_account("PROJ-1")
        assert result is False


@pytest.mark.asyncio
class TestJiraClientLabel:
    async def test_add_label_success(self):
        client = _client()
        with patch.object(client, "_request", new_callable=AsyncMock) as mock:
            mock.return_value = _mock_response(204)
            result = await client.add_label("PROJ-1", "errand-processed")
        assert result is True


@pytest.mark.asyncio
class TestJiraClientCredentialError:
    async def test_401_raises_credential_error(self):
        client = _client()
        with patch("platforms.jira.client.httpx.AsyncClient") as mock_cls:
            mock_http = MagicMock()
            mock_resp = _mock_response(401)
            mock_http.request = AsyncMock(return_value=mock_resp)
            mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_http)
            mock_cls.return_value.__aexit__ = AsyncMock(return_value=False)

            with pytest.raises(JiraCredentialError):
                await client.add_comment("PROJ-1", "test")
