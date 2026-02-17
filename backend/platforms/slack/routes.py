"""FastAPI router for Slack endpoints."""
from urllib.parse import parse_qs

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_session
from platforms.credentials import load_credentials
from platforms.slack.blocks import help_blocks
from platforms.slack.handlers import (
    handle_list,
    handle_new,
    handle_output,
    handle_run,
    handle_status,
)
from platforms.slack.identity import resolve_slack_email
from platforms.slack.verification import verify_slack_request

router = APIRouter(prefix="/slack", tags=["slack"])


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
async def slack_events(request: Request):
    """Handle Slack Events API (URL verification only for now)."""
    data = await request.json()
    if data.get("type") == "url_verification":
        return {"challenge": data["challenge"]}
    return JSONResponse(content={"ok": True}, status_code=200)
