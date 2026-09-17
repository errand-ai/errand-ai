"""Intake clarification: settle what a task means before it exists.

A description goes in; the classifier either resolves it or asks up to three
outcome-changing questions. Answers are folded back in and the classifier is
asked again, at most `clarification_max_rounds` times, after which the draft is
ready whatever is still open. Confirming turns the draft into an ordinary task
through the same code `POST /api/tasks` uses, so nothing downstream can tell the
difference.

Web and Slack both call this module; neither re-implements any of it.
"""
import asyncio
import logging
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from llm import VALID_CATEGORIES, ProfileInfo, _fallback_title, generate_title
from models import Task, TaskProfile, TaskSpecDraft
from settings_registry import resolve_setting_value
from task_creation import create_task_from_fields

logger = logging.getLogger(__name__)

DRAFT_TTL = timedelta(hours=24)
ACTIVE_STATUSES = ("drafting", "ready")
SPEC_FIELDS = ("title", "description", "category", "execute_at", "repeat_interval", "repeat_until", "profile")


class DraftNotFound(Exception):
    """No such draft for this owner, or it has expired. Deliberately one error:
    a draft belonging to somebody else is not disclosed."""


class DraftFinished(Exception):
    """The draft can no longer be advanced (confirmed, abandoned, or nothing to answer)."""


class DraftBusy(DraftFinished):
    """Another answer to the same round got there first. The draft is still
    live; this request simply lost the race."""


def owner_identity(claims: dict) -> str:
    """The identity a web caller's drafts belong to: what `created_by` records."""
    return claims.get("email") or claims.get("sub") or ""


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _aware(value: datetime) -> datetime:
    # SQLite hands timezone-aware columns back naive; they were written as UTC.
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def parse_draft_id(draft_id) -> uuid.UUID:
    if isinstance(draft_id, uuid.UUID):
        return draft_id
    try:
        return uuid.UUID(str(draft_id))
    except (TypeError, ValueError):
        raise DraftNotFound(str(draft_id))


def _turn(role: str, content: str) -> dict:
    return {"role": role, "content": content, "ts": _now().isoformat()}


async def max_rounds(session: AsyncSession) -> int:
    value, _ = await resolve_setting_value(session, "clarification_max_rounds")
    return max(1, int(value))


async def _load(session: AsyncSession, draft_id, owner: str) -> TaskSpecDraft:
    draft = await session.get(TaskSpecDraft, parse_draft_id(draft_id))
    if draft is None or draft.owner_id != owner or _aware(draft.expires_at) <= _now():
        raise DraftNotFound(str(draft_id))
    return draft


def _answered_clarifications(draft: TaskSpecDraft) -> list[str]:
    # Every user turn after the first is a set of answers.
    user_turns = [t for t in draft.conversation if t.get("role") == "user"]
    return [t["content"] for t in user_turns[1:]]


def _composed_description(draft: TaskSpecDraft) -> str:
    """The input plus whatever the user has answered — what runs when the
    classifier left no description of its own."""
    answers = _answered_clarifications(draft)
    if not answers:
        return draft.input_text
    return draft.input_text + "\n\nClarifications:\n" + "\n".join(answers)


def _resolved_fields(draft: TaskSpecDraft) -> dict:
    """The spec as it would run now: gaps filled the way `confirm` fills them."""
    spec = draft.spec or {}
    category = spec.get("category")
    return {
        "title": spec.get("title") or _fallback_title(draft.input_text),
        "description": spec.get("description") or _composed_description(draft),
        "category": category if category in VALID_CATEGORIES else "immediate",
        "execute_at": spec.get("execute_at"),
        "repeat_interval": spec.get("repeat_interval"),
        "repeat_until": spec.get("repeat_until"),
        "profile": spec.get("profile"),
    }


def draft_view(draft: TaskSpecDraft, rounds: int) -> dict:
    return {
        "id": str(draft.id),
        "status": draft.status,
        "source": draft.source,
        "input": draft.input_text,
        "questions": draft.questions or [],
        "questions_unresolved": draft.questions_unresolved,
        "spec_preview": _resolved_fields(draft),
        "round": draft.round,
        "max_rounds": rounds,
        "conversation": draft.conversation,
        "created_at": _aware(draft.created_at).isoformat() if draft.created_at else None,
        "expires_at": _aware(draft.expires_at).isoformat(),
        "resolved_task_id": str(draft.resolved_task_id) if draft.resolved_task_id else None,
    }


async def _profiles(session: AsyncSession) -> list[ProfileInfo] | None:
    result = await session.execute(select(TaskProfile).order_by(TaskProfile.name))
    profiles = result.scalars().all()
    return [ProfileInfo(name=p.name, match_rules=p.match_rules) for p in profiles] or None


def _spec_value(value):
    # Models write "null" as a string often enough to matter: it would be shown
    # in the preview and stored as a repeat interval.
    if isinstance(value, str) and value.strip().lower() in ("", "null", "none"):
        return None
    return value


async def _classify(session: AsyncSession, draft: TaskSpecDraft, cap_reached: bool) -> None:
    """Ask the classifier about the draft as it stands and record its answer."""
    history = [
        {"role": t["role"], "content": t["content"]}
        for t in draft.conversation[1:]
        if t.get("role") in ("user", "assistant")
    ]
    result = await generate_title(
        draft.input_text,
        session,
        now=_now(),
        profiles=await _profiles(session),
        want_questions=True,
        history=history or None,
    )

    if not result.success:
        # Unreached or unusable. There is nobody to ask a question on our
        # behalf, so the user decides from the preview; the answers they have
        # given are kept, folded into the description.
        logger.info("Intake classification unavailable for draft %s (%s)", draft.id, result.cause)
        draft.spec = {}
        questions = None
    else:
        draft.spec = {field: _spec_value(getattr(result, field)) for field in SPEC_FIELDS}
        questions = result.questions

    if questions and not cap_reached:
        draft.status = "drafting"
        draft.questions = questions
        draft.questions_unresolved = False
        content = "\n".join(q["text"] for q in questions)
    else:
        draft.status = "ready"
        # At the cap, the open questions stay visible as context — never as
        # something more to answer.
        draft.questions = questions if questions else None
        draft.questions_unresolved = bool(questions)
        content = f"Ready: {_resolved_fields(draft)['title']}"
    draft.conversation = [*draft.conversation, _turn("assistant", content)]


async def start(session: AsyncSession, input_text: str, owner: str, source: str = "web") -> TaskSpecDraft:
    input_text = input_text.strip()
    draft = TaskSpecDraft(
        id=uuid.uuid4(),
        owner_id=owner,
        source=source,
        input_text=input_text,
        conversation=[_turn("user", input_text)],
        spec={},
        status="drafting",
        round=0,
        expires_at=_now() + DRAFT_TTL,
    )
    session.add(draft)
    await _classify(session, draft, cap_reached=False)
    await session.commit()
    return draft


async def answer(session: AsyncSession, draft_id, owner: str, responses: dict) -> TaskSpecDraft:
    draft = await _load(session, draft_id, owner)
    if draft.status != "drafting" or not draft.questions:
        raise DraftFinished("This draft has no open questions")

    lines = []
    for question in draft.questions:
        value = responses.get(question["id"])
        if isinstance(value, str) and value.strip():
            lines.append(f"{question['text']} -> {value.strip()}")
    content = "\n".join(lines) or "(no answer given)"

    # Claim this round before the slow classifier call, as `confirm` claims the
    # draft: a second Submit (or a redelivered Slack action) would otherwise
    # pass the same status check and the later commit would drop one answer.
    # On Postgres the losing request waits on the row lock, then matches nothing.
    claimed = await session.execute(
        update(TaskSpecDraft)
        .where(
            TaskSpecDraft.id == draft.id,
            TaskSpecDraft.status == "drafting",
            TaskSpecDraft.round == draft.round,
        )
        .values(round=draft.round + 1)
        .execution_options(synchronize_session=False)
    )
    if claimed.rowcount != 1:
        await session.rollback()
        raise DraftBusy("This draft was just answered; reload it to see where it stands")

    draft.conversation = [*draft.conversation, _turn("user", content)]
    draft.round += 1
    draft.expires_at = _now() + DRAFT_TTL

    await _classify(session, draft, cap_reached=draft.round >= await max_rounds(session))
    await session.commit()
    return draft


def _parse_datetime(value) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except (TypeError, ValueError):
        return None


async def confirm(session: AsyncSession, draft_id, owner: str, extra_tags: tuple[str, ...] = ()) -> Task:
    draft = await _load(session, draft_id, owner)
    # Claimed with a conditional update rather than a read-then-write, so two
    # clicks on Run cannot both get past this line and create two tasks.
    claimed = await session.execute(
        update(TaskSpecDraft)
        .where(TaskSpecDraft.id == draft.id, TaskSpecDraft.status.in_(ACTIVE_STATUSES))
        .values(status="confirmed", updated_at=_now())
        .execution_options(synchronize_session=False)
    )
    if claimed.rowcount != 1:
        await session.rollback()
        raise DraftFinished("This draft has already been confirmed or cancelled")

    fields = _resolved_fields(draft)
    profile_id = None
    if fields["profile"]:
        profile_id = (
            await session.execute(select(TaskProfile.id).where(TaskProfile.name == fields["profile"]))
        ).scalar_one_or_none()

    # No "Needs Info": the user has seen the preview and chosen to run it.
    task = await create_task_from_fields(
        session,
        title=fields["title"],
        description=fields["description"],
        category=fields["category"],
        execute_at=_parse_datetime(fields["execute_at"]),
        repeat_interval=fields["repeat_interval"],
        repeat_until=_parse_datetime(fields["repeat_until"]),
        profile_id=profile_id,
        created_by=owner,
        tag_names=list(extra_tags),
        classification="clarified",
    )

    await session.refresh(draft)
    draft.resolved_task_id = task.id
    await session.commit()
    return task


async def cancel(session: AsyncSession, draft_id, owner: str) -> TaskSpecDraft:
    draft = await _load(session, draft_id, owner)
    if draft.status not in ACTIVE_STATUSES:
        raise DraftFinished("This draft has already been confirmed or cancelled")
    draft.status = "abandoned"
    await session.commit()
    return draft


async def get(session: AsyncSession, draft_id, owner: str) -> TaskSpecDraft:
    return await _load(session, draft_id, owner)


async def list_active(session: AsyncSession, owner: str) -> list[TaskSpecDraft]:
    result = await session.execute(
        select(TaskSpecDraft)
        .where(
            TaskSpecDraft.owner_id == owner,
            TaskSpecDraft.status.in_(ACTIVE_STATUSES),
            TaskSpecDraft.expires_at > _now(),
        )
        .order_by(TaskSpecDraft.created_at.desc())
    )
    return list(result.scalars().all())


async def sweep_expired_drafts(session: AsyncSession) -> tuple[int, int]:
    """Abandon expired drafts, and delete abandoned ones a day past expiry.

    Returns (abandoned, deleted).
    """
    now = _now()
    abandoned = await session.execute(
        update(TaskSpecDraft)
        .where(TaskSpecDraft.status.in_(ACTIVE_STATUSES), TaskSpecDraft.expires_at <= now)
        .values(status="abandoned")
        .execution_options(synchronize_session=False)
    )
    deleted = await session.execute(
        delete(TaskSpecDraft)
        .where(TaskSpecDraft.status == "abandoned", TaskSpecDraft.expires_at <= now - DRAFT_TTL)
        .execution_options(synchronize_session=False)
    )
    await session.commit()
    return abandoned.rowcount, deleted.rowcount


DRAFT_SWEEP_INTERVAL_SECONDS = 3600


async def run_draft_sweeper(session_factory, interval: float = DRAFT_SWEEP_INTERVAL_SECONDS) -> None:
    """Sweep at startup, then hourly. Drafts are cheap and nothing reads an
    expired one, so the cadence only bounds how long a stale row lingers."""
    while True:
        try:
            async with session_factory() as session:
                abandoned, deleted = await sweep_expired_drafts(session)
            if abandoned or deleted:
                logger.info("Draft sweep: %d abandoned, %d deleted", abandoned, deleted)
        except Exception:
            logger.exception("Draft sweep failed")
        await asyncio.sleep(interval)
