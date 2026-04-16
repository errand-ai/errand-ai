"""GitHub webhook handler for Projects V2 integration.

Parses GitHub projects_v2_item webhook payloads, evaluates trigger filters,
creates errand tasks with external references on match.
"""

import json
import logging

from sqlalchemy import insert, select

from database import async_session
from models import ExternalTaskRef, Tag, Task, WebhookTrigger, task_tags
from platforms.github.client import GitHubClient, GitHubClientError
from platforms.github.prompt import render_prompt

logger = logging.getLogger(__name__)


def parse_github_payload(body: bytes) -> dict | None:
    """Parse and validate a GitHub projects_v2_item webhook payload.

    Returns extracted fields or None if the payload is invalid.
    """
    try:
        data = json.loads(body)
    except (json.JSONDecodeError, UnicodeDecodeError):
        logger.warning("Invalid JSON in GitHub webhook payload")
        return None

    action = data.get("action")
    item = data.get("projects_v2_item")
    if not action or not item:
        logger.warning("GitHub webhook missing action or projects_v2_item")
        return None

    changes = data.get("changes", {})
    field_value = changes.get("field_value", {})

    return {
        "action": action,
        "item_node_id": item.get("node_id", ""),
        "project_node_id": item.get("project_node_id", ""),
        "content_node_id": item.get("content_node_id", ""),
        "content_type": item.get("content_type", ""),
        "field_name": field_value.get("field_name", ""),
        "from_name": (field_value.get("from") or {}).get("name", ""),
        "to_name": (field_value.get("to") or {}).get("name", ""),
        "organization_login": (data.get("organization") or {}).get("login", ""),
        "sender_login": (data.get("sender") or {}).get("login", ""),
    }


def evaluate_filters(trigger: WebhookTrigger, payload: dict) -> bool:
    """Evaluate trigger filters against the parsed payload. Returns True if all pass."""
    filters = trigger.filters or {}

    # Must be an "edited" action on the "Status" field
    if payload["action"] != "edited" or payload["field_name"] != "Status":
        return False

    # project_node_id must match
    if payload["project_node_id"] != filters.get("project_node_id", ""):
        return False

    # to_name must match trigger_column (case-insensitive)
    trigger_column = filters.get("trigger_column", "")
    if payload["to_name"].lower() != trigger_column.lower():
        return False

    # content_type must be in allowed types
    content_types = filters.get("content_types", ["Issue"])
    if payload["content_type"] not in content_types:
        return False

    return True


async def handle_github_webhook(trigger: WebhookTrigger, body: bytes, headers: dict) -> None:
    """Process a GitHub projects_v2_item webhook payload for a matched trigger."""
    payload = parse_github_payload(body)
    if not payload:
        logger.info("GitHub webhook payload could not be parsed for trigger %s", trigger.id)
        return

    if not evaluate_filters(trigger, payload):
        logger.info(
            "GitHub webhook did not pass filters for trigger %s "
            "(action=%s, field=%s, to=%s, content_type=%s, project=%s)",
            trigger.id,
            payload["action"], payload["field_name"],
            payload["to_name"], payload["content_type"],
            payload["project_node_id"],
        )
        return

    content_node_id = payload["content_node_id"]

    async with async_session() as session:
        # Create client from credentials
        try:
            client = await GitHubClient.from_credentials(session)
        except GitHubClientError as e:
            logger.error("Failed to create GitHub client: %s", e)
            return

        # Resolve the issue details
        try:
            issue = await client.resolve_issue(content_node_id)
        except GitHubClientError as e:
            logger.warning(
                "Could not resolve issue for node %s: %s", content_node_id, e
            )
            return

        repo_owner = issue["repo_owner"]
        repo_name = issue["repo_name"]
        number = issue["number"]
        external_id = f"{repo_owner}/{repo_name}#{number}"

        # Deduplication: matches DB unique constraint (external_id, source)
        existing = await session.execute(
            select(ExternalTaskRef).where(
                ExternalTaskRef.external_id == external_id,
                ExternalTaskRef.source == "github",
            )
        )
        if existing.scalar_one_or_none():
            logger.info("Task already exists for GitHub issue %s, skipping", external_id)
            return

        # Get or create the "github" tag
        tag_result = await session.execute(select(Tag).where(Tag.name == "github"))
        github_tag = tag_result.scalar_one_or_none()
        if not github_tag:
            github_tag = Tag(name="github")
            session.add(github_tag)
            await session.flush()

        # Render system prompt as task description
        description = render_prompt(
            issue_number=number,
            issue_title=issue["title"],
            repo_owner=repo_owner,
            repo_name=repo_name,
            issue_url=issue["url"],
            issue_labels=issue["labels"],
            errand_task_id="<pending>",  # Updated after flush
            task_prompt=trigger.task_prompt,
        )

        # Create task
        task = Task(
            title=f"{repo_owner}/{repo_name}#{number}: {issue['title']}",
            description=description,
            status="pending",
            profile_id=trigger.profile_id,
            created_by=f"github:{external_id}",
        )
        session.add(task)
        await session.flush()

        # Update description with actual task ID
        task.description = task.description.replace("<pending>", str(task.id))

        # Associate tag
        await session.execute(
            insert(task_tags).values(task_id=task.id, tag_id=github_tag.id)
        )

        # Create ExternalTaskRef
        ref = ExternalTaskRef(
            task_id=task.id,
            trigger_id=trigger.id,
            source="github",
            external_id=external_id,
            external_url=issue["url"],
            metadata_={
                "project_node_id": payload["project_node_id"],
                "item_node_id": payload["item_node_id"],
                "content_node_id": content_node_id,
                "repo_owner": repo_owner,
                "repo_name": repo_name,
                "issue_labels": issue["labels"],
            },
        )
        session.add(ref)
        await session.commit()

        logger.info(
            "Created task %s for GitHub issue %s (trigger=%s)",
            task.id, external_id, trigger.id,
        )

        # Try to post a comment on the issue (best-effort, never aborts)
        try:
            import os
            base_url = os.environ.get("PUBLIC_BASE_URL", "").rstrip("/")
            task_link = f"[{task.id}]({base_url}/tasks/{task.id})" if base_url else str(task.id)
            await client.add_comment(
                content_node_id,
                f"Errand task created: {task_link}",
            )
        except Exception:
            logger.warning("Failed to comment on issue %s", external_id, exc_info=True)
