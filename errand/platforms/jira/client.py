"""Jira REST API client for completion actions.

Uses httpx with Bearer token auth against the Atlassian Cloud gateway.
"""

import logging
from typing import Optional

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from platforms.credentials import load_credentials

logger = logging.getLogger(__name__)

# Cached service account ID (resolved once, reused)
_account_id_cache: dict[str, str] = {}

MAX_COMMENT_SIZE = 30_000  # 30KB, leaving margin for ADF wrapper


class JiraCredentialError(Exception):
    """Raised when Jira credentials are missing or invalid (401)."""
    pass


class JiraClient:
    """Httpx-based Jira API client."""

    def __init__(self, cloud_id: str, api_token: str, service_account_email: str = ""):
        self.base_url = f"https://api.atlassian.com/ex/jira/{cloud_id}/rest/api/3"
        self.headers = {
            "Authorization": f"Bearer {api_token}",
            "Content-Type": "application/json",
        }
        self.service_account_email = service_account_email

    @classmethod
    async def from_credentials(cls, session: AsyncSession) -> "JiraClient":
        """Create a JiraClient from stored PlatformCredentials."""
        creds = await load_credentials("jira", session)
        if not creds:
            raise JiraCredentialError("No Jira credentials configured")
        return cls(
            cloud_id=creds["cloud_id"],
            api_token=creds["api_token"],
            service_account_email=creds.get("service_account_email", ""),
        )

    async def _request(self, method: str, path: str, **kwargs) -> httpx.Response:
        """Make an API request, raising JiraCredentialError on 401."""
        async with httpx.AsyncClient() as client:
            resp = await client.request(
                method,
                f"{self.base_url}{path}",
                headers=self.headers,
                timeout=30,
                **kwargs,
            )
        if resp.status_code == 401:
            raise JiraCredentialError(f"Jira returned 401 — credentials may be invalid")
        return resp

    async def add_comment(self, issue_key: str, text: str) -> bool:
        """Post a comment on a Jira issue. Returns True on success."""
        # Truncate to max size
        if len(text) > MAX_COMMENT_SIZE:
            text = text[:MAX_COMMENT_SIZE] + "\n\n[output truncated]"

        adf_body = {
            "body": {
                "version": 1,
                "type": "doc",
                "content": [
                    {
                        "type": "paragraph",
                        "content": [{"type": "text", "text": text}],
                    }
                ],
            }
        }
        resp = await self._request("POST", f"/issue/{issue_key}/comment", json=adf_body)
        if not resp.is_success:
            logger.error("Failed to add comment to %s: %s %s", issue_key, resp.status_code, resp.text)
            return False
        return True

    async def transition_issue(self, issue_key: str, target_name: str) -> bool:
        """Transition a Jira issue to the target status name. Returns True on success."""
        # Get available transitions
        resp = await self._request("GET", f"/issue/{issue_key}/transitions")
        if not resp.is_success:
            logger.error("Failed to get transitions for %s: %s", issue_key, resp.status_code)
            return False

        transitions = resp.json().get("transitions", [])
        matched = None
        for t in transitions:
            if t.get("name", "").lower() == target_name.lower():
                matched = t
                break

        if not matched:
            available = [t.get("name", "") for t in transitions]
            logger.warning(
                "Transition '%s' not available for %s. Available: %s",
                target_name, issue_key, available,
            )
            return False

        resp = await self._request(
            "POST",
            f"/issue/{issue_key}/transitions",
            json={"transition": {"id": matched["id"]}},
        )
        if not resp.is_success:
            logger.error("Failed to transition %s: %s %s", issue_key, resp.status_code, resp.text)
            return False
        return True

    async def assign_to_service_account(self, issue_key: str) -> bool:
        """Assign a Jira issue to the service account. Returns True on success."""
        account_id = await self._resolve_account_id()
        if not account_id:
            logger.error("Cannot assign %s — service account ID not resolved", issue_key)
            return False

        resp = await self._request(
            "PUT",
            f"/issue/{issue_key}/assignee",
            json={"accountId": account_id},
        )
        if not resp.is_success:
            logger.error("Failed to assign %s: %s %s", issue_key, resp.status_code, resp.text)
            return False
        return True

    async def _resolve_account_id(self) -> Optional[str]:
        """Resolve the service account email to an Atlassian account ID (cached)."""
        if not self.service_account_email:
            logger.error("No service account email configured")
            return None

        if self.service_account_email in _account_id_cache:
            return _account_id_cache[self.service_account_email]

        resp = await self._request(
            "GET",
            "/user/search",
            params={"query": self.service_account_email},
        )
        if not resp.is_success:
            logger.error("User search failed: %s", resp.status_code)
            return None

        users = resp.json()
        if not users:
            logger.error("No Jira user found for email %s", self.service_account_email)
            return None

        account_id = users[0].get("accountId")
        if account_id:
            _account_id_cache[self.service_account_email] = account_id
        return account_id

    async def add_label(self, issue_key: str, label: str) -> bool:
        """Add a label to a Jira issue. Returns True on success."""
        resp = await self._request(
            "PUT",
            f"/issue/{issue_key}",
            json={"update": {"labels": [{"add": label}]}},
        )
        if not resp.is_success:
            logger.error("Failed to add label to %s: %s %s", issue_key, resp.status_code, resp.text)
            return False
        return True
