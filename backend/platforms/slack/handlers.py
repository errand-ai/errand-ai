"""Slack command handler functions."""
import uuid
from datetime import datetime, timezone

from sqlalchemy import cast, func, select, String
from sqlalchemy.ext.asyncio import AsyncSession

from models import Task
from platforms.slack.blocks import (
    error_blocks,
    task_created_blocks,
    task_list_blocks,
    task_output_blocks,
    task_status_blocks,
)


async def find_task_by_prefix(prefix: str, session: AsyncSession) -> Task | dict:
    """Find task by UUID or prefix. Returns Task or error_blocks dict."""
    prefix = prefix.strip()
    if not prefix:
        return error_blocks("Please provide a task ID or prefix")

    # Try full UUID first
    try:
        task_uuid = uuid.UUID(prefix)
        result = await session.execute(select(Task).where(Task.id == task_uuid))
        task = result.scalar_one_or_none()
        if task:
            return task
        return error_blocks(f"No task found with ID `{prefix}`")
    except ValueError:
        pass

    # Try prefix match
    result = await session.execute(
        select(Task).where(cast(Task.id, String).like(f"{prefix}%"))
    )
    matches = result.scalars().all()

    if len(matches) == 0:
        return error_blocks(f"No task found matching `{prefix}`")
    if len(matches) == 1:
        return matches[0]

    lines = [f"`{str(t.id)[:8]}` {t.title}" for t in matches[:5]]
    return error_blocks(
        f"Ambiguous prefix `{prefix}` \u2014 matches {len(matches)} tasks:\n" + "\n".join(lines)
    )


async def handle_new(args: str, user_email: str, session: AsyncSession) -> dict:
    """Create a new task. Returns Block Kit response dict."""
    if not args.strip():
        return error_blocks("Usage: `/task new <title>`")

    max_pos_result = await session.execute(
        select(func.max(Task.position)).where(Task.status == "pending")
    )
    position = (max_pos_result.scalar() or 0) + 1

    task = Task(
        title=args.strip(),
        created_by=user_email,
        category="immediate",
        status="pending",
        position=position,
    )
    session.add(task)
    await session.commit()
    await session.refresh(task)
    return task_created_blocks(task)


async def handle_status(args: str, session: AsyncSession) -> dict:
    """Get task status. Returns Block Kit response dict."""
    if not args.strip():
        return error_blocks("Usage: `/task status <id>`")

    result = await find_task_by_prefix(args.strip(), session)
    if isinstance(result, dict):
        return result
    return task_status_blocks(result)


async def handle_list(args: str, session: AsyncSession) -> dict:
    """List tasks. Returns Block Kit response dict."""
    status_filter = args.strip() if args.strip() else None
    query = select(Task)
    if status_filter:
        query = query.where(Task.status == status_filter)
    else:
        query = query.where(Task.status.not_in(["deleted", "archived"]))
    query = query.order_by(Task.position.asc(), Task.created_at.asc())
    result = await session.execute(query)
    tasks = list(result.scalars().all())
    return task_list_blocks(tasks, status_filter)


async def handle_run(args: str, user_email: str, session: AsyncSession) -> dict:
    """Queue a task for execution. Returns Block Kit response dict."""
    if not args.strip():
        return error_blocks("Usage: `/task run <id>`")

    result = await find_task_by_prefix(args.strip(), session)
    if isinstance(result, dict):
        return result

    task = result
    if task.status in ("running", "pending"):
        return error_blocks(f"Task is already `{task.status}`")

    task.status = "pending"
    task.updated_by = user_email
    await session.commit()
    await session.refresh(task)
    return {
        "response_type": "ephemeral",
        "blocks": [
            {
                "type": "section",
                "text": {"type": "mrkdwn", "text": f":rocket: Task `{str(task.id)[:8]}` queued for execution"},
            },
        ],
    }


async def handle_output(args: str, session: AsyncSession) -> dict:
    """Get task output. Returns Block Kit response dict."""
    if not args.strip():
        return error_blocks("Usage: `/task output <id>`")

    result = await find_task_by_prefix(args.strip(), session)
    if isinstance(result, dict):
        return result
    return task_output_blocks(result)
