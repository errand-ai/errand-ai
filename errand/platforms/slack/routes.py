"""FastAPI router for Slack endpoints."""
import asyncio
import json
import logging
import re
import time
from datetime import datetime, timezone
from urllib.parse import parse_qs

from fastapi import APIRouter, BackgroundTasks, Depends, Request
from fastapi.responses import JSONResponse
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from database import async_session, get_session
from events import publish_event
from llm import generate_title
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
_BOT_MENTION_RE = re.compile(r"<@[A-Z0-9]+(?:\|[^>|]+)?>\s*")


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


async def process_slack_command(body: bytes, session: AsyncSession, use_response_url: str | None = None) -> dict:
    """Process a Slack slash command payload.

    Parses form data, dispatches to subcommand handlers, and handles channel message posting.
    When use_response_url is provided (cloud relay path), POSTs the response to that URL
    instead of returning it as the HTTP response.
    Called directly by the cloud webhook dispatcher (no signature verification).
    """
    form_data = parse_qs(body.decode())
    text = form_data.get("text", [""])[0]
    user_id = form_data.get("user_id", [""])[0]
    channel_id = form_data.get("channel_id", [""])[0]

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

    # If a task was just created, also post a channel message for live status updates
    task_id = response.pop("_task_id", None)
    if task_id and bot_token and channel_id:
        asyncio.create_task(
            _post_channel_message_and_store_ref(
                bot_token=bot_token,
                channel_id=channel_id,
                task_id=task_id,
                blocks=response.get("blocks", []),
            )
        )

    # For cloud relay: send response via response_url instead of returning it
    if use_response_url:
        response_url = form_data.get("response_url", [""])[0]
        if response_url:
            asyncio.create_task(
                _post_interaction_response(
                    response_url=response_url,
                    blocks=response.get("blocks", []),
                )
            )
        else:
            logger.warning("Cloud relay command missing response_url, discarding response")
        return {"ok": True}

    return response


@router.post("/commands")
async def slack_commands(
    background_tasks: BackgroundTasks,
    body: bytes = Depends(verify_slack_request),
    session: AsyncSession = Depends(get_session),
):
    """Handle Slack slash commands."""
    response = await process_slack_command(body, session)
    return JSONResponse(content=response)


async def process_slack_event(body: bytes) -> dict | None:
    """Process a Slack event payload (event_callback with app_mention).

    Handles duplicate detection and background task creation.
    Returns a response dict for HTTP use, or None for cloud dispatch.
    Called directly by the cloud webhook dispatcher (no signature verification).
    """
    data = json.loads(body)

    if data.get("type") == "event_callback":
        event = data.get("event", {})
        event_id = data.get("event_id", "")

        if event.get("type") == "app_mention":
            if event_id and not _is_duplicate_event(event_id):
                asyncio.create_task(_handle_mention(event=event))

    return {"ok": True}


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

    result = await process_slack_event(body)
    return JSONResponse(content=result or {"ok": True}, status_code=200)


async def _handle_mention(event: dict) -> None:
    """Process an app_mention event: create task, post confirmation, store message ref."""
    text = event.get("text", "")
    user_id = event.get("user", "")
    channel = event.get("channel", "")

    # Strip bot mention to get input text
    input_text = _BOT_MENTION_RE.sub("", text).strip()
    if not input_text:
        return  # Empty mention, silently ignore

    async with async_session() as session:
        # Load credentials for bot token
        credentials = await load_credentials("slack", session)
        bot_token = credentials.get("bot_token", "") if credentials else ""

        # Resolve user email
        email = await resolve_slack_email(user_id, bot_token) if user_id and bot_token else None
        user_email = email or f"slack:{user_id}"

        # Generate title via LLM for longer inputs
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

        # Create task
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


async def process_slack_interaction(body: bytes, session: AsyncSession) -> dict:
    """Process a Slack interactivity payload (button clicks).

    Parses the payload and dispatches block_actions, posting responses
    to response_url. This function already uses response_url for delivery.
    Called directly by the cloud webhook dispatcher (no signature verification).
    """
    form_data = parse_qs(body.decode())
    payload_str = form_data.get("payload", [""])[0]
    if not payload_str:
        return {"ok": True}

    try:
        payload = json.loads(payload_str)
    except (json.JSONDecodeError, TypeError):
        return {"ok": True}

    if payload.get("type") == "block_actions":
        response_url = payload.get("response_url", "")
        actions = payload.get("actions", [])
        for action in actions:
            action_id = action.get("action_id")
            task_id = action.get("value", "")

            if action_id in ("task_status", "task_output"):
                if action_id == "task_status":
                    response = await handle_status(task_id, session)
                else:
                    response = await handle_output(task_id, session)

                if response_url:
                    asyncio.create_task(
                        _post_interaction_response(
                            response_url=response_url,
                            blocks=response.get("blocks", []),
                        )
                    )
                break

    return {"ok": True}


@router.post("/interactions")
async def slack_interactions(
    background_tasks: BackgroundTasks,
    body: bytes = Depends(verify_slack_request),
    session: AsyncSession = Depends(get_session),
):
    """Handle Slack interactivity payloads (button clicks).

    For block_actions, the direct HTTP response only acknowledges receipt.
    Actual responses are sent via the response_url as ephemeral messages,
    since response_type is only honoured when posted to response_url.
    """
    result = await process_slack_interaction(body, session)
    return JSONResponse(content=result, status_code=200)


async def _post_channel_message_and_store_ref(
    bot_token: str, channel_id: str, task_id: str, blocks: list,
) -> None:
    """Post a visible channel message for a new task and store the ref for live updates."""
    try:
        resp = await _slack_client.post_message(bot_token, channel_id, blocks)
        if resp.get("ok"):
            async with async_session() as session:
                msg_ref = SlackMessageRef(
                    task_id=task_id,
                    channel_id=resp.get("channel", channel_id),
                    message_ts=resp["ts"],
                )
                session.add(msg_ref)
                await session.commit()
    except Exception:
        logger.exception("Failed to post channel message for task %s", task_id)


async def _post_interaction_response(response_url: str, blocks: list) -> None:
    """Post an ephemeral response to a Slack interaction response_url."""
    try:
        await _slack_client.post_response_url(response_url, blocks)
    except Exception:
        logger.exception("Failed to post interaction response to %s", response_url)
