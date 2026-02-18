"""Slack command handler functions."""
import uuid
from datetime import datetime, timezone

from sqlalchemy import cast, func, select, String
from sqlalchemy.ext.asyncio import AsyncSession

from events import publish_event
from llm import generate_title
from models import Task
from platforms.slack.blocks import (
    error_blocks,
    task_created_blocks,
    task_list_blocks,
    task_output_blocks,
    task_status_blocks,
)
from tags import add_tag


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

    # Try prefix match — escape SQL wildcard characters in user input
    safe_prefix = prefix.replace("%", "\\%").replace("_", "\\_")
    result = await session.execute(
        select(Task).where(cast(Task.id, String).like(f"{safe_prefix}%"))
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
    input_text = args.strip()
    if not input_text:
        return error_blocks("Usage: `/task new <title>`")

    words = input_text.split()
    title = input_text
    description = None
    category = "immediate"
    execute_at = None
    tag_names: list[str] = []

    if len(words) > 5:
        llm_result = await generate_title(input_text, session, now=datetime.now(timezone.utc))
        title = llm_result.title
        description = input_text
        category = llm_result.category or "immediate"
        if llm_result.execute_at:
            try:
                execute_at = datetime.fromisoformat(llm_result.execute_at)
            except (ValueError, TypeError):
                pass  # LLM returned unparseable date; fall back to default scheduling
        if not llm_result.success:
            tag_names.append("Needs Info")
    else:
        tag_names.append("Needs Info")

    if category == "immediate":
        execute_at = datetime.now(timezone.utc)

    max_pos_result = await session.execute(
        select(func.max(Task.position)).where(Task.status == "pending")
    )
    position = (max_pos_result.scalar() or 0) + 1

    task = Task(
        title=title,
        description=description,
        created_by=user_email,
        category=category,
        status="pending",
        position=position,
        execute_at=execute_at,
    )
    session.add(task)
    await session.flush()
    await add_tag(session, task.id, "slack")
    for tag_name in tag_names:
        await add_tag(session, task.id, tag_name)
    await session.commit()
    await session.refresh(task)

    # Notify WebSocket clients
    all_tags = ["slack"] + tag_names
    await publish_event("task_created", {
        "id": str(task.id),
        "title": task.title,
        "description": task.description,
        "status": task.status,
        "position": task.position,
        "category": task.category,
        "execute_at": task.execute_at.isoformat() if task.execute_at else None,
        "repeat_interval": task.repeat_interval,
        "repeat_until": None,
        "output": None,
        "runner_logs": None,
        "questions": None,
        "retry_count": 0,
        "tags": sorted(all_tags),
        "created_at": task.created_at.isoformat() if task.created_at else None,
        "updated_at": task.updated_at.isoformat() if task.updated_at else None,
        "created_by": task.created_by,
        "updated_by": task.updated_by,
    })

    response = task_created_blocks(task)
    response["_task_id"] = str(task.id)  # metadata for route (stripped before sending)
    return response


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
