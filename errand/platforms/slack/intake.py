"""Slack intake: `/task new` and `@`-mentions go through clarification.

The questions arrive as input blocks on a message, and the answers come back
as a `block_actions` payload on the interactions endpoint. The app subscribes
only to `app_mention`, so a plain thread reply would never reach us; input
blocks need no further event subscriptions or scopes.
"""
import logging

from sqlalchemy.ext.asyncio import AsyncSession

import clarify
from database import async_session
from models import SlackMessageRef, TaskSpecDraft
from platforms.credentials import load_credentials
from platforms.slack.blocks import (
    TASK_SPEC_ANSWER,
    TASK_SPEC_CANCEL,
    TASK_SPEC_QUESTION_BLOCK_PREFIX,
    TASK_SPEC_RUN,
    TASK_SPEC_SUBMIT,
    task_created_blocks,
    task_spec_draft_blocks,
    task_spec_notice_blocks,
)
from platforms.slack.client import SlackClient
from platforms.slack.identity import resolve_slack_email

logger = logging.getLogger(__name__)

_slack_client = SlackClient()

INACTIVE_NOTICE = ":information_source: This draft is no longer active. Start a new one with `/task new`."
NOT_YOURS_NOTICE = ":lock: Only the person who started this draft can answer or run it."


async def bot_token(session: AsyncSession) -> str:
    credentials = await load_credentials("slack", session)
    return credentials.get("bot_token", "") if credentials else ""


async def slack_owner(user_id: str, token: str) -> str:
    """The identity a Slack user's drafts and tasks belong to — as `created_by` records it."""
    email = await resolve_slack_email(user_id, token) if user_id and token else None
    return email or f"slack:{user_id}"


async def start_draft(session: AsyncSession, text: str, owner: str) -> tuple[TaskSpecDraft, list]:
    draft = await clarify.start(session, text, owner, source="slack")
    return draft, task_spec_draft_blocks(clarify.draft_view(draft, await clarify.max_rounds(session)))


async def start_mention_draft(session: AsyncSession, text: str, owner: str, token: str, channel: str, ts: str) -> None:
    """Start a draft from a mention and post it in the mention's thread."""
    draft, blocks = await start_draft(session, text, owner)
    try:
        resp = await _slack_client.post_message(
            token, channel, blocks, text="A few details before I start", thread_ts=ts or None,
        )
    except Exception:
        logger.exception("Failed to post task draft to channel %s", channel)
        return
    if resp.get("ok"):
        draft.external_channel_id = resp.get("channel", channel)
        draft.external_message_ts = resp.get("ts")
        await session.commit()


def answers_from_state(values: dict) -> dict[str, str]:
    """Answers keyed by question id, from a block_actions payload's `state.values`."""
    answers: dict[str, str] = {}
    for block_id, elements in (values or {}).items():
        if not block_id.startswith(TASK_SPEC_QUESTION_BLOCK_PREFIX) or not isinstance(elements, dict):
            continue
        element = elements.get(TASK_SPEC_ANSWER) or {}
        value = element.get("value")
        if value is None:
            value = (element.get("selected_option") or {}).get("value")
        if isinstance(value, str):
            answers[block_id[len(TASK_SPEC_QUESTION_BLOCK_PREFIX):]] = value
    return answers


async def _reply(response_url: str, blocks: list, *, replace: bool) -> None:
    if not response_url:
        return
    try:
        await _slack_client.post_response_url(response_url, blocks, replace_original=replace)
    except Exception:
        logger.exception("Failed to post task draft response")


async def _belongs_to_someone_else(session: AsyncSession, draft_id: str, owner: str) -> bool:
    try:
        draft = await session.get(TaskSpecDraft, clarify.parse_draft_id(draft_id))
    except clarify.DraftNotFound:
        return False
    return draft is not None and draft.owner_id != owner


async def _link_task_message(session: AsyncSession, token: str, draft: TaskSpecDraft, task, channel_id: str) -> None:
    """Give the new task a Slack message the status updater can keep current.

    A mention's draft was a real channel message, now replaced by the task
    confirmation, so it is that message. A slash command's draft was ephemeral,
    which cannot be updated later, so a visible one is posted — as `/task new`
    always has.
    """
    channel, ts = draft.external_channel_id, draft.external_message_ts
    if not ts and token and channel_id:
        try:
            resp = await _slack_client.post_message(token, channel_id, task_created_blocks(task)["blocks"])
        except Exception:
            logger.exception("Failed to post channel message for task %s", task.id)
            return
        if not resp.get("ok"):
            return
        channel, ts = resp.get("channel", channel_id), resp.get("ts")
    if channel and ts:
        session.add(SlackMessageRef(task_id=task.id, channel_id=channel, message_ts=ts))
        await session.commit()


async def handle_draft_action(payload: dict, action: dict, session_factory=None) -> None:
    """Carry out Submit / Run / Cancel for a draft message. Runs after the
    interaction has been acknowledged: a classifier call can outlast Slack's
    three-second window."""
    session_factory = session_factory or async_session
    response_url = payload.get("response_url", "")
    action_id = action.get("action_id")
    draft_id = action.get("value", "")
    user_id = (payload.get("user") or {}).get("id", "")
    channel_id = (payload.get("channel") or {}).get("id", "")

    async with session_factory() as session:
        token = await bot_token(session)
        owner = await slack_owner(user_id, token)
        try:
            if action_id == TASK_SPEC_SUBMIT:
                answers = answers_from_state((payload.get("state") or {}).get("values") or {})
                draft = await clarify.answer(session, draft_id, owner, answers)
                view = clarify.draft_view(draft, await clarify.max_rounds(session))
                await _reply(response_url, task_spec_draft_blocks(view), replace=True)
            elif action_id == TASK_SPEC_RUN:
                task = await clarify.confirm(session, draft_id, owner, extra_tags=("slack",))
                await _reply(response_url, task_created_blocks(task)["blocks"], replace=True)
                draft = await clarify.get(session, draft_id, owner)
                await _link_task_message(session, token, draft, task, channel_id)
            elif action_id == TASK_SPEC_CANCEL:
                await clarify.cancel(session, draft_id, owner)
                await _reply(response_url, task_spec_notice_blocks(":x: Draft cancelled."), replace=True)
        except clarify.DraftNotFound:
            await session.rollback()
            if await _belongs_to_someone_else(session, draft_id, owner):
                await _reply(response_url, task_spec_notice_blocks(NOT_YOURS_NOTICE), replace=False)
            else:
                await _reply(response_url, task_spec_notice_blocks(INACTIVE_NOTICE), replace=True)
        except clarify.DraftFinished:
            await _reply(response_url, task_spec_notice_blocks(INACTIVE_NOTICE), replace=True)
        except Exception:
            logger.exception("Task draft action %s failed for draft %s", action_id, draft_id)
            await _reply(
                response_url,
                task_spec_notice_blocks(":warning: Something went wrong with this draft. Please try again."),
                replace=False,
            )
