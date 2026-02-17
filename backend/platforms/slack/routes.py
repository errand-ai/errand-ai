"""FastAPI router for Slack endpoints."""
import json
import logging
import re
import time
from urllib.parse import parse_qs

from fastapi import APIRouter, BackgroundTasks, Depends, Request
from fastapi.responses import JSONResponse
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from database import async_session, get_session
from models import SlackMessageRef, Task
from platforms.credentials import load_credentials
from platforms.slack.blocks import help_blocks, task_created_blocks
from platforms.slack.client import SlackClient
from platforms.slack.handlers import (
    handle_list,
    handle_new,
    handle_output,
    handle_run,
    handle_status,
)
from platforms.slack.identity import resolve_slack_email
from platforms.slack.verification import verify_slack_request
from tags import add_tag

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/slack", tags=["slack"])

# In-memory TTL cache for duplicate event prevention
_processed_events: dict[str, float] = {}
_EVENT_TTL = 300  # 5 minutes

_slack_client = SlackClient()

# Regex to strip bot mention from text: <@BOTID> or <@BOTID|botname>
_BOT_MENTION_RE = re.compile(r"<@[A-Z0-9]+(?:\|[^>]+)?>\s*")


def _is_duplicate_event(event_id: str) -> bool:
    """Check if event was already processed (within TTL). Also cleans expired entries."""
    now = time.time()

    # Clean expired entries
    expired = [k for k, v in _processed_events.items() if now - v > _EVENT_TTL]
    for k in expired:
        del _processed_events[k]

    if event_id in _processed_events:
        return True

    _processed_events[event_id] = now
    return False


@router.post("/commands")
async def slack_commands(
    body: bytes = Depends(verify_slack_request),
    session: AsyncSession = Depends(get_session),
):
    """Handle Slack slash commands."""
    form_data = parse_qs(body.decode())
    text = form_data.get("text", [""])[0]
    user_id = form_data.get("user_id", [""])[0]

    # Parse subcommand
    parts = text.split(None, 1)
    subcommand = parts[0].lower() if parts else ""
    args = parts[1] if len(parts) > 1 else ""

    # Resolve user email
    credentials = await load_credentials("slack", session)
    bot_token = credentials.get("bot_token", "") if credentials else ""
    email = await resolve_slack_email(user_id, bot_token) if user_id and bot_token else None
    user_email = email or f"slack:{user_id}"

    # Dispatch
    if subcommand == "new":
        response = await handle_new(args, user_email, session)
    elif subcommand == "status":
        response = await handle_status(args, session)
    elif subcommand == "list":
        response = await handle_list(args, session)
    elif subcommand == "run":
        response = await handle_run(args, user_email, session)
    elif subcommand == "output":
        response = await handle_output(args, session)
    else:
        response = help_blocks()

    return JSONResponse(content=response)


@router.post("/events")
async def slack_events(
    request: Request,
    background_tasks: BackgroundTasks,
    body: bytes = Depends(verify_slack_request),
):
    """Handle Slack Events API (URL verification + app_mention events)."""
    data = json.loads(body)

    if data.get("type") == "url_verification":
        return {"challenge": data["challenge"]}

    if data.get("type") == "event_callback":
        event = data.get("event", {})
        event_id = data.get("event_id", "")

        if event.get("type") == "app_mention":
            if not _is_duplicate_event(event_id):
                background_tasks.add_task(
                    _handle_mention,
                    event=event,
                )

    return JSONResponse(content={"ok": True}, status_code=200)


async def _handle_mention(event: dict) -> None:
    """Process an app_mention event: create task, post confirmation, store message ref."""
    text = event.get("text", "")
    user_id = event.get("user", "")
    channel = event.get("channel", "")

    # Strip bot mention to get task title
    title = _BOT_MENTION_RE.sub("", text).strip()
    if not title:
        return  # Empty mention, silently ignore

    async with async_session() as session:
        # Load credentials for bot token
        credentials = await load_credentials("slack", session)
        bot_token = credentials.get("bot_token", "") if credentials else ""

        # Resolve user email
        email = await resolve_slack_email(user_id, bot_token) if user_id and bot_token else None
        user_email = email or f"slack:{user_id}"

        # Create task
        max_pos_result = await session.execute(
            select(func.max(Task.position)).where(Task.status == "pending")
        )
        position = (max_pos_result.scalar() or 0) + 1

        task = Task(
            title=title,
            created_by=user_email,
            category="immediate",
            status="pending",
            position=position,
        )
        session.add(task)
        await session.flush()
        await add_tag(session, task.id, "slack")
        await session.commit()
        await session.refresh(task)

        # Post confirmation to channel
        try:
            blocks_data = task_created_blocks(task)
            resp = await _slack_client.post_message(bot_token, channel, blocks_data["blocks"])
            if resp.get("ok"):
                # Store message reference for later updates
                msg_ref = SlackMessageRef(
                    task_id=task.id,
                    channel_id=resp.get("channel", channel),
                    message_ts=resp["ts"],
                )
                session.add(msg_ref)
                await session.commit()
        except Exception:
            logger.exception("Failed to post mention confirmation to channel %s", channel)


@router.post("/interactions")
async def slack_interactions(
    body: bytes = Depends(verify_slack_request),
    session: AsyncSession = Depends(get_session),
):
    """Handle Slack interactivity payloads (button clicks)."""
    form_data = parse_qs(body.decode())
    payload_str = form_data.get("payload", [""])[0]
    if not payload_str:
        return JSONResponse(content={"ok": True}, status_code=200)

    payload = json.loads(payload_str)

    if payload.get("type") == "block_actions":
        actions = payload.get("actions", [])
        for action in actions:
            action_id = action.get("action_id")
            task_id = action.get("value", "")

            if action_id == "task_status":
                response = await handle_status(task_id, session)
                return JSONResponse(content=response)
            elif action_id == "task_output":
                response = await handle_output(task_id, session)
                return JSONResponse(content=response)

    # Unknown action or type — acknowledge with 200
    return JSONResponse(content={"ok": True}, status_code=200)
