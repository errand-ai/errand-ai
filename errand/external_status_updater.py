"""Valkey subscriber that dispatches external system callbacks on task status changes.

Follows the same pattern as platforms/slack/status_updater.py but for webhook triggers.
"""

import asyncio
import json
import logging
import uuid as uuid_mod

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models import ExternalTaskRef, WebhookTrigger
from platforms.jira.client import JiraClient, JiraCredentialError

logger = logging.getLogger(__name__)


async def _process_task_event(data: dict, session: AsyncSession) -> None:
    """Process a task event and dispatch external callbacks if applicable."""
    task_data = data.get("task", {})
    task_id_str = task_data.get("id")
    if not task_id_str:
        return

    try:
        task_id = uuid_mod.UUID(task_id_str)
    except (ValueError, TypeError):
        return

    # Look up ExternalTaskRef
    result = await session.execute(
        select(ExternalTaskRef).where(ExternalTaskRef.task_id == task_id)
    )
    ref = result.scalar_one_or_none()
    if not ref:
        return  # Not an externally-triggered task

    if not ref.trigger_id:
        logger.debug("ExternalTaskRef %s has no trigger (deleted), skipping callback", ref.id)
        return

    # Load the trigger
    result = await session.execute(
        select(WebhookTrigger).where(WebhookTrigger.id == ref.trigger_id)
    )
    trigger = result.scalar_one_or_none()
    if not trigger:
        logger.debug("Trigger %s not found for ref %s, skipping callback", ref.trigger_id, ref.id)
        return

    status = task_data.get("status", "")
    output = task_data.get("output", "")
    actions = trigger.actions or {}

    try:
        if ref.source == "jira":
            await _dispatch_jira(ref, trigger, actions, task_data, status, output, session)
        else:
            logger.warning("No callback handler registered for source: %s", ref.source)
    except JiraCredentialError:
        logger.warning("Jira credentials invalid, skipping remaining actions for task %s", task_id)
    except Exception:
        logger.exception("Error dispatching callback for task %s (source=%s)", task_id, ref.source)


async def _dispatch_jira(
    ref: ExternalTaskRef,
    trigger: WebhookTrigger,
    actions: dict,
    task_data: dict,
    status: str,
    output: str,
    session: AsyncSession,
) -> None:
    """Dispatch Jira-specific callbacks based on trigger actions and status."""
    issue_key = ref.external_id
    task_id = task_data.get("id", "unknown")
    errors: list[str] = []

    try:
        jira = await JiraClient.from_credentials(session)
    except JiraCredentialError:
        logger.warning("No Jira credentials configured, skipping callbacks for %s", issue_key)
        return

    if status == "running":
        if actions.get("add_comment"):
            if not await jira.add_comment(issue_key, f"Task started by Errand (task ID: {task_id})"):
                errors.append("add_comment failed on running")
        if actions.get("assign_to"):
            if not await jira.assign_to_service_account(issue_key):
                errors.append("assign_to failed on running")

    elif status == "completed":
        if actions.get("comment_output") or actions.get("add_comment"):
            comment = f"Task completed by Errand (task ID: {task_id})"
            if output and actions.get("comment_output"):
                comment += f"\n\n{output}"
            if not await jira.add_comment(issue_key, comment):
                errors.append("add_comment failed on completed")
        if actions.get("transition_on_complete"):
            if not await jira.transition_issue(issue_key, actions["transition_on_complete"]):
                errors.append(f"transition_on_complete '{actions['transition_on_complete']}' failed")
        if actions.get("add_label"):
            if not await jira.add_label(issue_key, actions["add_label"]):
                errors.append(f"add_label '{actions['add_label']}' failed")

    elif status == "failed":
        if actions.get("add_comment"):
            error_msg = output or "No error details available"
            if not await jira.add_comment(
                issue_key,
                f"Task failed in Errand (task ID: {task_id})\n\n{error_msg}",
            ):
                errors.append("add_comment failed on failed")

    # Store action errors in ExternalTaskRef metadata for debugging
    if errors:
        metadata = dict(ref.metadata_) if ref.metadata_ else {}
        metadata["action_errors"] = errors
        ref.metadata_ = metadata
        await session.commit()


async def run_external_status_updater(
    get_valkey_fn,
    async_session_maker,
    channel: str = "task_events",
) -> None:
    """Subscribe to task events and dispatch external callbacks.

    Runs as a long-lived background task. Reconnects on connection loss.
    """
    pubsub = None
    while True:
        try:
            valkey = get_valkey_fn()
            if valkey is None:
                await asyncio.sleep(5)
                continue

            pubsub = valkey.pubsub()
            await pubsub.subscribe(channel)
            logger.info("External status updater subscribed to %s", channel)

            while True:
                msg = await pubsub.get_message(ignore_subscribe_messages=True, timeout=1.0)
                if msg and msg["type"] == "message":
                    try:
                        data = json.loads(msg["data"])
                    except (json.JSONDecodeError, TypeError):
                        continue

                    if data.get("event") == "task_updated":
                        async with async_session_maker() as session:
                            await _process_task_event(data, session)

        except asyncio.CancelledError:
            logger.info("External status updater shutting down")
            if pubsub is not None:
                try:
                    await pubsub.unsubscribe(channel)
                    await pubsub.aclose()
                except Exception:
                    logger.debug("Error cleaning up pubsub on shutdown", exc_info=True)
            raise
        except Exception:
            logger.exception("External status updater error, reconnecting in 5s")
            await asyncio.sleep(5)
