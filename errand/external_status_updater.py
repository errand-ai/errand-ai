"""Valkey subscriber that dispatches external system callbacks on task status changes.

Follows the same pattern as platforms/slack/status_updater.py but for webhook triggers.
"""

import asyncio
import json
import logging
import re
import uuid as uuid_mod

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models import ExternalTaskRef, Task, WebhookTrigger
from platforms.github.client import GitHubClient, GitHubClientError
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
        elif ref.source == "github":
            await _dispatch_github(ref, trigger, actions, task_data, status, output, session)
        else:
            logger.warning("No callback handler registered for source: %s", ref.source)
    except (JiraCredentialError, GitHubClientError):
        logger.warning("Credentials invalid, skipping remaining actions for task %s", task_id)
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


def _parse_structured_output(output: str | None) -> dict | None:
    """Extract a fenced JSON block from task output."""
    if not output:
        return None
    match = re.search(r"```json\s*\n(.*?)```", output, re.DOTALL)
    if not match:
        return None
    try:
        return json.loads(match.group(1))
    except (json.JSONDecodeError, TypeError):
        return None


async def _dispatch_github(
    ref: ExternalTaskRef,
    trigger: WebhookTrigger,
    actions: dict,
    task_data: dict,
    status: str,
    output: str,
    session: AsyncSession,
) -> None:
    """Dispatch GitHub-specific callbacks based on trigger actions and status."""
    task_id = task_data.get("id", "unknown")
    errors: list[str] = []

    client = await GitHubClient.from_credentials(session)

    if status == "running":
        if actions.get("column_on_running"):
            column_name = actions["column_on_running"]
            option_id = actions.get("column_options", {}).get(column_name)
            if option_id:
                try:
                    await client.update_item_status(
                        ref.metadata_["project_node_id"],
                        ref.metadata_["item_node_id"],
                        actions["project_field_id"],
                        option_id,
                    )
                except Exception:
                    logger.exception("Failed to update column to %s for task %s", column_name, task_id)
                    errors.append(f"column_on_running '{column_name}' failed")
            else:
                logger.warning("Column '%s' not found in cached column_options for task %s", column_name, task_id)

        if actions.get("add_comment"):
            try:
                await client.add_comment(
                    ref.metadata_["content_node_id"],
                    f"Errand task started (task ID: {task_id})",
                )
            except Exception:
                logger.exception("Failed to post running comment for task %s", task_id)
                errors.append("add_comment failed on running")

    elif status == "completed":
        structured = _parse_structured_output(output)

        if actions.get("comment_output") or actions.get("add_comment"):
            try:
                if structured and structured.get("status") != "aborted":
                    summary = structured.get("summary", "Task completed.")
                    await client.add_comment(
                        ref.metadata_["content_node_id"],
                        f"Errand task completed (task ID: {task_id})\n\n{summary}",
                    )
                elif not structured:
                    await client.add_comment(
                        ref.metadata_["content_node_id"],
                        f"Errand task completed (task ID: {task_id})",
                    )
            except Exception:
                logger.exception("Failed to post completion comment for task %s", task_id)
                errors.append("comment failed on completed")

        if structured and structured.get("status") == "aborted":
            try:
                reason = structured.get("reason", "No reason provided")
                await client.add_comment(
                    ref.metadata_["content_node_id"],
                    f"Errand task aborted (task ID: {task_id})\n\nReason: {reason}",
                )
            except Exception:
                logger.exception("Failed to post abort comment for task %s", task_id)
                errors.append("abort comment failed")
            # Skip review + column actions on abort
            if errors:
                metadata = dict(ref.metadata_) if ref.metadata_ else {}
                metadata["action_errors"] = errors
                ref.metadata_ = metadata
                await session.commit()
            return

        if actions.get("copilot_review") and structured and structured.get("pr_number"):
            try:
                await client.request_review(
                    ref.metadata_["repo_owner"],
                    ref.metadata_["repo_name"],
                    structured["pr_number"],
                    ["copilot"],
                )
            except Exception:
                logger.exception("Failed to request copilot review for task %s", task_id)
                errors.append("copilot_review failed")

        if actions.get("review_profile_id") and structured and structured.get("pr_url") and structured.get("branch"):
            pr_number = structured.get("pr_number", "")
            repo_owner = ref.metadata_.get("repo_owner", "")
            repo_name = ref.metadata_.get("repo_name", "")
            review_task = Task(
                title=f"Review: {repo_owner}/{repo_name}#{pr_number}",
                description=(
                    f"Review PR {structured['pr_url']}\n"
                    f"Branch: {structured['branch']}\n"
                    f"Issue: {ref.external_url}"
                ),
                status="pending",
                profile_id=uuid_mod.UUID(actions["review_profile_id"]),
                created_by=f"github:review:{ref.external_id}",
            )
            session.add(review_task)
            await session.flush()
            review_metadata = dict(ref.metadata_) if ref.metadata_ else {}
            review_metadata["parent_external_id"] = ref.external_id
            review_ref = ExternalTaskRef(
                task_id=review_task.id,
                trigger_id=ref.trigger_id,
                source="github",
                external_id=f"{ref.external_id}:review:{review_task.id}",
                external_url=ref.external_url,
                metadata_=review_metadata,
            )
            session.add(review_ref)
            await session.commit()

        if actions.get("column_on_complete"):
            column_name = actions["column_on_complete"]
            option_id = actions.get("column_options", {}).get(column_name)
            if option_id:
                try:
                    await client.update_item_status(
                        ref.metadata_["project_node_id"],
                        ref.metadata_["item_node_id"],
                        actions["project_field_id"],
                        option_id,
                    )
                except Exception:
                    logger.exception("Failed to update column to %s for task %s", column_name, task_id)
                    errors.append(f"column_on_complete '{column_name}' failed")
            else:
                logger.warning("Column '%s' not found in cached column_options for task %s", column_name, task_id)

    elif status == "failed":
        if actions.get("add_comment"):
            try:
                error_msg = output or "No error details available"
                await client.add_comment(
                    ref.metadata_["content_node_id"],
                    f"Errand task failed (task ID: {task_id})\n\n{error_msg}",
                )
            except Exception:
                logger.exception("Failed to post failure comment for task %s", task_id)
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
