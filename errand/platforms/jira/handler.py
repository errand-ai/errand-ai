"""Jira webhook handler.

Parses Jira webhook payloads, evaluates trigger filters,
creates errand tasks with external references on match.
"""

import json
import logging

from sqlalchemy import select

from database import async_session
from models import ExternalTaskRef, Tag, Task, WebhookTrigger, task_tags

logger = logging.getLogger(__name__)


def parse_jira_payload(body: bytes) -> dict | None:
    """Parse and validate a Jira webhook payload. Returns extracted fields or None."""
    try:
        data = json.loads(body)
    except (json.JSONDecodeError, UnicodeDecodeError):
        logger.warning("Invalid JSON in Jira webhook payload")
        return None

    event = data.get("webhookEvent")
    issue = data.get("issue")
    if not event or not issue:
        logger.warning("Jira webhook missing webhookEvent or issue")
        return None

    fields = issue.get("fields")
    if not fields:
        logger.warning("Jira webhook issue missing fields")
        return None

    return {
        "event": event,
        "issue_key": issue.get("key", ""),
        "issue_self": issue.get("self", ""),
        "summary": fields.get("summary", ""),
        "description": fields.get("description"),
        "issue_type": (fields.get("issuetype") or {}).get("name", ""),
        "labels": fields.get("labels", []),
        "project_key": (fields.get("project") or {}).get("key", ""),
        "parent_key": (fields.get("parent") or {}).get("key"),
        "reporter": (fields.get("reporter") or {}).get("displayName", ""),
        "priority": (fields.get("priority") or {}).get("name", ""),
        "changelog": data.get("changelog"),
    }


def evaluate_filters(trigger: WebhookTrigger, payload: dict) -> bool:
    """Evaluate trigger filters against the parsed payload. Returns True if all pass."""
    filters = trigger.filters or {}

    # event_types filter
    event_types = filters.get("event_types", [])
    if event_types and payload["event"] not in event_types:
        return False

    # issue_types filter (case-insensitive)
    issue_types = filters.get("issue_types", [])
    if issue_types:
        issue_type_lower = payload["issue_type"].lower()
        if not any(t.lower() == issue_type_lower for t in issue_types):
            return False

    # labels filter
    trigger_labels = filters.get("labels", [])
    if trigger_labels:
        if payload["event"] == "jira:issue_created":
            # On create: check if any trigger label is in issue labels
            if not any(lbl in trigger_labels for lbl in payload["labels"]):
                return False
        elif payload["event"] == "jira:issue_updated":
            # On update: check changelog for label addition
            if not _label_just_added(payload, trigger_labels):
                return False
        else:
            # Other events: check current labels
            if not any(lbl in trigger_labels for lbl in payload["labels"]):
                return False

    # projects filter
    projects = filters.get("projects", [])
    if projects and payload["project_key"] not in projects:
        return False

    return True


def _label_just_added(payload: dict, trigger_labels: list[str]) -> bool:
    """Check if a matching label was just added in the changelog."""
    changelog = payload.get("changelog")
    if not changelog:
        return False
    items = changelog.get("items", [])
    for item in items:
        if item.get("field") == "labels":
            to_str = item.get("toString", "")
            from_str = item.get("fromString", "")
            to_labels = set(to_str.split()) if to_str else set()
            from_labels = set(from_str.split()) if from_str else set()
            added_labels = to_labels - from_labels
            if any(lbl in added_labels for lbl in trigger_labels):
                return True
    return False


def _build_description(payload: dict) -> str:
    """Build task description from Jira payload."""
    parts = []
    if payload.get("description"):
        desc = payload["description"]
        # Jira Cloud may send ADF (dict) or plain text
        if isinstance(desc, dict):
            parts.append("[Jira issue description in ADF format]")
        else:
            parts.append(str(desc))

    metadata = []
    if payload.get("reporter"):
        metadata.append(f"Reporter: {payload['reporter']}")
    if payload.get("priority"):
        metadata.append(f"Priority: {payload['priority']}")
    if payload.get("parent_key"):
        metadata.append(f"Parent: {payload['parent_key']}")

    if metadata:
        parts.append("\n---\n" + "\n".join(metadata))

    return "\n\n".join(parts) if parts else ""


async def handle_jira_webhook(trigger: WebhookTrigger, body: bytes, headers: dict) -> None:
    """Process a Jira webhook payload for a matched trigger."""
    payload = parse_jira_payload(body)
    if not payload:
        logger.info("Jira webhook payload could not be parsed for trigger %s", trigger.id)
        return

    if not evaluate_filters(trigger, payload):
        logger.info(
            "Jira webhook %s did not pass filters for trigger %s "
            "(event=%s, issue_type=%s, labels=%s, project=%s)",
            payload["issue_key"], trigger.id,
            payload["event"], payload["issue_type"],
            payload["labels"], payload["project_key"],
        )
        return

    issue_key = payload["issue_key"]

    async with async_session() as session:
        # Deduplication: check if we already have a ref for this external item
        existing = await session.execute(
            select(ExternalTaskRef).where(
                ExternalTaskRef.external_id == issue_key,
                ExternalTaskRef.source == "jira",
            )
        )
        if existing.scalar_one_or_none():
            logger.info("Task already exists for Jira issue %s, skipping", issue_key)
            return

        # Load Jira credentials for cloud_id and browsable URL
        from platforms.credentials import load_credentials
        jira_creds = await load_credentials("jira", session)
        cloud_id = jira_creds.get("cloud_id", "") if jira_creds else ""
        site_url = (jira_creds.get("site_url", "") if jira_creds else "").rstrip("/")
        browsable_url = f"{site_url}/browse/{issue_key}" if site_url else payload["issue_self"]

        # Get or create the "jira" tag
        tag_result = await session.execute(select(Tag).where(Tag.name == "jira"))
        jira_tag = tag_result.scalar_one_or_none()
        if not jira_tag:
            jira_tag = Tag(name="jira")
            session.add(jira_tag)
            await session.flush()

        # Create task
        task = Task(
            title=f"{issue_key}: {payload['summary']}",
            description=_build_description(payload),
            status="pending",
            profile_id=trigger.profile_id,
            created_by=f"jira:{issue_key}",
        )
        session.add(task)
        await session.flush()

        # Associate tag
        from sqlalchemy import insert
        await session.execute(
            insert(task_tags).values(task_id=task.id, tag_id=jira_tag.id)
        )

        # Create ExternalTaskRef
        ref_metadata = {"project_key": payload["project_key"]}
        if cloud_id:
            ref_metadata["cloud_id"] = cloud_id
        ref = ExternalTaskRef(
            task_id=task.id,
            trigger_id=trigger.id,
            source="jira",
            external_id=issue_key,
            external_url=browsable_url,
            parent_id=payload.get("parent_key"),
            metadata_=ref_metadata,
        )
        session.add(ref)
        await session.commit()

        logger.info(
            "Created task %s for Jira issue %s (trigger=%s)",
            task.id, issue_key, trigger.id,
        )
