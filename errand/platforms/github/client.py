"""GitHub GraphQL and REST API client for Projects V2 integration."""

import logging
from typing import Any, Optional

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from platforms.credentials import load_credentials
from platforms.github.platform import GITHUB_API_BASE, mint_installation_token
from platforms.github import queries

logger = logging.getLogger(__name__)

GRAPHQL_URL = "https://api.github.com/graphql"


class GitHubClientError(Exception):
    """Raised when a GitHub API call fails."""
    pass


class GitHubClient:
    """Async client for GitHub GraphQL and REST APIs."""

    def __init__(self, token: str):
        self._token = token
        self._headers = {
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "Content-Type": "application/json",
        }

    @classmethod
    async def from_credentials(cls, session: AsyncSession) -> "GitHubClient":
        """Create a GitHubClient from stored platform credentials."""
        creds = await load_credentials("github", session)
        if not creds:
            raise GitHubClientError("No GitHub credentials configured")

        auth_mode = creds.get("auth_mode", "pat")
        if auth_mode == "pat":
            token = creds.get("personal_access_token", "")
            if not token:
                raise GitHubClientError("GitHub PAT is empty")
        elif auth_mode == "app":
            try:
                token = mint_installation_token(
                    app_id=creds["app_id"],
                    private_key=creds["private_key"],
                    installation_id=creds["installation_id"],
                )
            except Exception as e:
                raise GitHubClientError(f"Failed to mint GitHub App token: {e}") from e
        else:
            raise GitHubClientError(f"Unknown GitHub auth_mode: {auth_mode}")

        return cls(token=token)

    async def _graphql(self, query: str, variables: dict | None = None) -> dict:
        """Execute a GraphQL query and return the data dict."""
        payload: dict[str, Any] = {"query": query}
        if variables:
            payload["variables"] = variables

        async with httpx.AsyncClient() as client:
            resp = await client.post(
                GRAPHQL_URL,
                headers=self._headers,
                json=payload,
                timeout=30,
            )

        if resp.status_code == 401:
            raise GitHubClientError("GitHub API returned 401 — credentials may be invalid")

        if resp.status_code != 200:
            raise GitHubClientError(f"GitHub GraphQL HTTP {resp.status_code}: {resp.text}")

        body = resp.json()
        if "errors" in body:
            messages = [e.get("message", str(e)) for e in body["errors"]]
            raise GitHubClientError(f"GitHub GraphQL errors: {'; '.join(messages)}")

        return body.get("data", {})

    async def _rest(self, method: str, path: str, **kwargs) -> httpx.Response:
        """Execute a REST API request."""
        async with httpx.AsyncClient() as client:
            resp = await client.request(
                method,
                f"{GITHUB_API_BASE}{path}",
                headers=self._headers,
                timeout=30,
                **kwargs,
            )
        return resp

    async def introspect_project(self, org: str, project_number: int) -> dict:
        """Introspect a GitHub ProjectV2 to discover its fields and status options.

        Returns dict with keys: project_node_id, title, fields (list of field dicts).
        For SingleSelectField types, each field includes options with id and name.
        """
        data = await self._graphql(
            queries.INTROSPECT_PROJECT,
            variables={"org": org, "number": project_number},
        )

        org_data = data.get("organization")
        if not org_data:
            raise GitHubClientError(f"Organization '{org}' not found or not accessible")

        project = org_data.get("projectV2")
        if not project:
            raise GitHubClientError(
                f"Project #{project_number} not found in organization '{org}'"
            )

        fields = []
        for node in (project.get("fields", {}).get("nodes") or []):
            field: dict[str, Any] = {
                "id": node.get("id", ""),
                "name": node.get("name", ""),
            }
            if "options" in node:
                field["type"] = "SingleSelectField"
                field["options"] = [
                    {"id": opt["id"], "name": opt["name"]}
                    for opt in node["options"]
                ]
            fields.append(field)

        return {
            "project_node_id": project["id"],
            "title": project.get("title", ""),
            "fields": fields,
        }

    async def resolve_issue(self, node_id: str) -> dict:
        """Resolve a GitHub issue's full details from its node ID.

        Returns dict with keys: number, title, body, state, url,
        repo_owner, repo_name, labels, assignees.
        Raises GitHubClientError if the node is not an Issue.
        """
        data = await self._graphql(
            queries.RESOLVE_ISSUE,
            variables={"nodeId": node_id},
        )

        node = data.get("node")
        if not node:
            raise GitHubClientError(f"Node '{node_id}' not found")

        typename = node.get("__typename", "")
        if typename == "DraftIssue":
            raise GitHubClientError(
                f"Node '{node_id}' is a DraftIssue ('{node.get('title', '')}'), not an Issue"
            )
        if typename != "Issue":
            raise GitHubClientError(f"Node '{node_id}' is a {typename}, not an Issue")

        repo = node.get("repository", {})
        return {
            "number": node.get("number"),
            "title": node.get("title", ""),
            "body": node.get("body", ""),
            "state": node.get("state", ""),
            "url": node.get("url", ""),
            "repo_owner": repo.get("owner", {}).get("login", ""),
            "repo_name": repo.get("name", ""),
            "labels": [l["name"] for l in (node.get("labels", {}).get("nodes") or [])],
            "assignees": [a["login"] for a in (node.get("assignees", {}).get("nodes") or [])],
        }

    async def find_project_item(
        self, issue_node_id: str, project_node_id: str
    ) -> Optional[dict]:
        """Find the ProjectV2Item for an issue within a specific project.

        Returns dict with keys: item_id, status_name, status_option_id.
        Returns None if the issue is not in the project.
        """
        data = await self._graphql(
            queries.FIND_PROJECT_ITEM,
            variables={"issueId": issue_node_id},
        )

        node = data.get("node", {})
        items = node.get("projectItems", {}).get("nodes", [])

        for item in items:
            if item.get("project", {}).get("id") == project_node_id:
                status_name = None
                status_option_id = None

                for fv in (item.get("fieldValues", {}).get("nodes") or []):
                    field = fv.get("field", {})
                    if field.get("name") == "Status":
                        status_name = fv.get("name")
                        status_option_id = fv.get("optionId")
                        break

                return {
                    "item_id": item["id"],
                    "status_name": status_name,
                    "status_option_id": status_option_id,
                }

        return None

    async def update_item_status(
        self, project_id: str, item_id: str, field_id: str, option_id: str
    ) -> None:
        """Update a project item's Status field value."""
        await self._graphql(
            queries.UPDATE_ITEM_FIELD_VALUE,
            variables={
                "input": {
                    "projectId": project_id,
                    "itemId": item_id,
                    "fieldId": field_id,
                    "value": {"singleSelectOptionId": option_id},
                }
            },
        )

    async def add_comment(self, subject_id: str, body: str) -> Optional[str]:
        """Add a comment to an issue or PR. Returns the comment URL or None."""
        data = await self._graphql(
            queries.ADD_COMMENT,
            variables={"subjectId": subject_id, "body": body},
        )

        comment_edge = data.get("addComment", {}).get("commentEdge", {})
        return comment_edge.get("node", {}).get("url")

    async def request_review(
        self, owner: str, repo: str, pull_number: int, reviewers: list[str]
    ) -> None:
        """Request reviewers on a pull request via REST API."""
        resp = await self._rest(
            "POST",
            f"/repos/{owner}/{repo}/pulls/{pull_number}/requested_reviewers",
            json={"reviewers": reviewers},
        )
        if resp.status_code == 422:
            logger.warning(
                "Review request returned 422 for PR %s/%s#%d reviewers=%s: %s",
                owner, repo, pull_number, reviewers, resp.text,
            )
        elif not resp.is_success:
            raise GitHubClientError(
                f"Failed to request review on {owner}/{repo}#{pull_number}: "
                f"HTTP {resp.status_code} {resp.text}"
            )
