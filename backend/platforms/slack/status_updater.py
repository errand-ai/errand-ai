"""Valkey subscriber that updates Slack messages when task status changes."""
import asyncio
import json
import logging
import uuid as uuid_mod
from types import SimpleNamespace

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models import SlackMessageRef
from platforms.slack.blocks import task_updated_blocks
from platforms.slack.client import SlackClient

logger = logging.getLogger(__name__)

_slack_client = SlackClient()


async def _process_task_event(data: dict, session: AsyncSession, bot_token: str) -> None:
    """Process a single task event and update the Slack message if applicable."""
    task_data = data.get("task", {})
    task_id_str = task_data.get("id")
    if not task_id_str:
        return

    try:
        task_id = uuid_mod.UUID(task_id_str)
    except (ValueError, TypeError):
        return

    # Look up message ref
    result = await session.execute(
        select(SlackMessageRef).where(SlackMessageRef.task_id == task_id)
    )
    msg_ref = result.scalar_one_or_none()
    if msg_ref is None:
        return  # No Slack message to update

    # Build a task-like object for the block builder
    task = SimpleNamespace(**task_data)

    try:
        blocks = task_updated_blocks(task)
        await _slack_client.update_message(
            bot_token, msg_ref.channel_id, msg_ref.message_ts, blocks
        )
    except Exception:
        logger.exception(
            "Failed to update Slack message for task %s (channel=%s, ts=%s) — deleting ref",
            task_id, msg_ref.channel_id, msg_ref.message_ts,
        )
        await session.delete(msg_ref)
        await session.commit()


async def run_status_updater(
    get_valkey_fn,
    async_session_maker,
    load_credentials_fn,
    channel: str = "task_events",
) -> None:
    """Subscribe to task events and update Slack messages on status changes.

    Runs as a long-lived background task. Reconnects on connection loss.
    """
    while True:
        try:
            valkey = get_valkey_fn()
            if valkey is None:
                await asyncio.sleep(5)
                continue

            pubsub = valkey.pubsub()
            await pubsub.subscribe(channel)
            logger.info("Slack status updater subscribed to %s", channel)

            while True:
                msg = await pubsub.get_message(ignore_subscribe_messages=True, timeout=1.0)
                if msg and msg["type"] == "message":
                    try:
                        data = json.loads(msg["data"])
                    except (json.JSONDecodeError, TypeError):
                        continue

                    if data.get("event") == "task_updated":
                        async with async_session_maker() as session:
                            credentials = await load_credentials_fn("slack", session)
                            bot_token = credentials.get("bot_token", "") if credentials else ""
                            if bot_token:
                                await _process_task_event(data, session, bot_token)

        except asyncio.CancelledError:
            logger.info("Slack status updater shutting down")
            try:
                await pubsub.unsubscribe(channel)
                await pubsub.aclose()
            except Exception:
                pass
            raise
        except Exception:
            logger.exception("Slack status updater error, reconnecting in 5s")
            await asyncio.sleep(5)
