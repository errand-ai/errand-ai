"""Intake clarification service (`clarify.py`)."""
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy import select

import clarify
from llm import CAUSE_NO_MODEL, CAUSE_UNUSABLE_RESPONSE, LLMResult
from models import Setting, Task, TaskProfile, TaskSpecDraft
from settings_registry import resolve_setting_value

OWNER = "alice@example.com"

QUESTIONS = [
    {"id": "source", "text": "Which spreadsheet holds the numbers?", "kind": "free_text"},
    {"id": "channel", "text": "Where should they go?", "kind": "choice", "choices": ["Email", "Slack"]},
]


def _ready(**overrides) -> LLMResult:
    fields = dict(
        title="Weekday Digest",
        success=True,
        category="repeating",
        execute_at="2026-09-18T09:00:00+00:00",
        repeat_interval="0 9 * * MON-FRI",
        description="Email me a digest of GitHub activity in errand-ai/errand",
    )
    fields.update(overrides)
    return LLMResult(**fields)


def _asking(questions=QUESTIONS) -> LLMResult:
    return LLMResult(
        title="Quarterly Numbers",
        success=True,
        description="Send the quarterly numbers",
        questions=questions,
    )


@pytest.fixture()
async def session(db_session):
    _, session_maker = db_session
    async with session_maker() as s:
        yield s


def _classifier(*results):
    return patch("clarify.generate_title", AsyncMock(side_effect=list(results)))


async def test_max_rounds_setting_defaults_to_two(session):
    assert await resolve_setting_value(session, "clarification_max_rounds") == (2, "default")
    assert await clarify.max_rounds(session) == 2


async def test_start_unambiguous_is_ready(session):
    with _classifier(_ready()) as classifier:
        draft = await clarify.start(session, "Every weekday at 9am, email me a digest", OWNER)

    view = clarify.draft_view(draft, 2)
    assert view["status"] == "ready"
    assert view["questions"] == []
    assert view["round"] == 0
    assert view["spec_preview"]["category"] == "repeating"
    assert view["spec_preview"]["repeat_interval"] == "0 9 * * MON-FRI"
    assert draft.owner_id == OWNER
    assert [t["role"] for t in draft.conversation] == ["user", "assistant"]
    assert classifier.call_args.kwargs["want_questions"] is True
    assert classifier.call_args.kwargs["history"] is None


async def test_start_ambiguous_asks_and_creates_no_task(session):
    with _classifier(_asking()):
        draft = await clarify.start(session, "Send me the quarterly numbers", OWNER)

    assert draft.status == "drafting"
    assert draft.questions == QUESTIONS
    assert draft.round == 0
    assert (await session.execute(select(Task))).scalars().all() == []


@pytest.mark.parametrize("cause", [CAUSE_NO_MODEL, CAUSE_UNUSABLE_RESPONSE])
async def test_start_without_usable_classifier_is_ready_with_raw_input(session, cause):
    with _classifier(LLMResult(title="garbage", success=False, cause=cause)):
        draft = await clarify.start(session, "Send me the quarterly numbers", OWNER)

    preview = clarify.draft_view(draft, 2)["spec_preview"]
    assert draft.status == "ready"
    assert draft.questions is None
    assert preview["description"] == "Send me the quarterly numbers"
    assert preview["title"] == "Send me the quarterly numbers..."
    assert preview["category"] == "immediate"


async def test_string_nulls_from_the_model_are_unset(session):
    with _classifier(_ready(category="immediate", execute_at="null", repeat_interval="None", repeat_until="", profile="null")):
        draft = await clarify.start(session, "Email me the numbers", OWNER)
    preview = clarify.draft_view(draft, 2)["spec_preview"]
    assert (preview["execute_at"], preview["repeat_interval"], preview["repeat_until"], preview["profile"]) == (None,) * 4
    with patch("task_creation.publish_event", AsyncMock()):
        task = await clarify.confirm(session, draft.id, OWNER)
    assert (await session.get(Task, task.id)).repeat_interval is None


async def test_answer_folds_answers_and_resolves(session):
    with _classifier(_asking(), _ready(title="Quarterly Numbers")) as classifier:
        draft = await clarify.start(session, "Send me the quarterly numbers", OWNER)
        draft = await clarify.answer(session, draft.id, OWNER, {"source": "Q3 finance", "channel": "Email", "bogus": "x"})

    assert draft.status == "ready"
    assert draft.round == 1
    assert draft.questions is None
    # Answering is activity: the 24h window starts again.
    assert clarify._aware(draft.expires_at) > datetime.now(timezone.utc) + timedelta(hours=23, minutes=59)
    history = classifier.call_args.kwargs["history"]
    assert history[-1] == {
        "role": "user",
        "content": "Which spreadsheet holds the numbers? -> Q3 finance\nWhere should they go? -> Email",
    }
    assert history[0]["role"] == "assistant"


async def test_round_cap_forces_ready_with_questions_unresolved(session):
    with _classifier(_asking(), _asking(), _asking()):
        draft = await clarify.start(session, "Send me the quarterly numbers", OWNER)
        draft = await clarify.answer(session, draft.id, OWNER, {"source": "the usual"})
        assert draft.status == "drafting"
        draft = await clarify.answer(session, draft.id, OWNER, {"source": "still the usual"})

    assert draft.round == 2
    assert draft.status == "ready"
    assert draft.questions_unresolved is True
    assert draft.questions == QUESTIONS
    with pytest.raises(clarify.DraftFinished):
        await clarify.answer(session, draft.id, OWNER, {"source": "again"})


async def test_round_cap_follows_setting(session):
    session.add(Setting(key="clarification_max_rounds", value=1))
    await session.commit()
    with _classifier(_asking(), _asking()):
        draft = await clarify.start(session, "Send me the quarterly numbers", OWNER)
        draft = await clarify.answer(session, draft.id, OWNER, {"source": "x"})
    assert draft.status == "ready"
    assert draft.questions_unresolved is True


async def test_other_owner_cannot_see_or_advance(session):
    with _classifier(_asking()):
        draft = await clarify.start(session, "Send me the quarterly numbers", OWNER)

    for call in (
        clarify.get(session, draft.id, "mallory@example.com"),
        clarify.answer(session, draft.id, "mallory@example.com", {"source": "x"}),
        clarify.confirm(session, draft.id, "mallory@example.com"),
        clarify.cancel(session, draft.id, "mallory@example.com"),
    ):
        with pytest.raises(clarify.DraftNotFound):
            await call
    await session.refresh(draft)
    assert draft.status == "drafting"
    assert draft.round == 0


async def test_malformed_id_is_not_found(session):
    with pytest.raises(clarify.DraftNotFound):
        await clarify.get(session, "not-a-uuid", OWNER)


async def test_confirm_creates_ordinary_task(session):
    session.add(TaskProfile(name="research", match_rules="research tasks"))
    await session.commit()
    with _classifier(_ready(profile="research")):
        draft = await clarify.start(session, "Every weekday at 9am, email me a digest", OWNER)

    with patch("task_creation.publish_event", AsyncMock()) as publish:
        task = await clarify.confirm(session, draft.id, OWNER, extra_tags=("slack",))

    await session.refresh(draft)
    assert draft.status == "confirmed"
    assert draft.resolved_task_id == task.id
    stored = await session.get(Task, task.id)
    assert stored.title == "Weekday Digest"
    assert stored.category == "repeating"
    assert stored.status == "scheduled"
    assert stored.repeat_interval == "0 9 * * MON-FRI"
    assert stored.created_by == OWNER
    assert stored.profile.name == "research"
    assert sorted(t.name for t in stored.tags) == ["slack"]
    publish.assert_awaited_once()
    assert publish.call_args.args[0] == "task_created"


async def test_just_run_it_confirms_a_drafting_draft(session):
    with _classifier(_asking()):
        draft = await clarify.start(session, "Send me the quarterly numbers", OWNER)
    assert draft.status == "drafting"
    with patch("task_creation.publish_event", AsyncMock()):
        task = await clarify.confirm(session, draft.id, OWNER)
    stored = await session.get(Task, task.id)
    assert stored.title == "Quarterly Numbers"
    assert stored.description == "Send the quarterly numbers"
    assert stored.status == "pending"


async def test_confirm_after_unusable_answer_keeps_answers_and_skips_needs_info(session):
    with _classifier(_asking(), LLMResult(title="x", success=False, cause=CAUSE_UNUSABLE_RESPONSE)):
        draft = await clarify.start(session, "Send me the quarterly numbers", OWNER)
        draft = await clarify.answer(session, draft.id, OWNER, {"source": "Q3 finance"})

    with patch("task_creation.publish_event", AsyncMock()):
        task = await clarify.confirm(session, draft.id, OWNER)

    stored = await session.get(Task, task.id)
    assert stored.status == "pending"
    assert stored.tags == []
    assert stored.description == (
        "Send me the quarterly numbers\n\nClarifications:\n"
        "Which spreadsheet holds the numbers? -> Q3 finance"
    )


async def test_confirm_twice_creates_one_task(session):
    with _classifier(_ready()):
        draft = await clarify.start(session, "Every weekday at 9am, email me a digest", OWNER)
    with patch("task_creation.publish_event", AsyncMock()):
        await clarify.confirm(session, draft.id, OWNER)
        with pytest.raises(clarify.DraftFinished):
            await clarify.confirm(session, draft.id, OWNER)
    assert len((await session.execute(select(Task))).scalars().all()) == 1


async def test_cancel_abandons(session):
    with _classifier(_asking()):
        draft = await clarify.start(session, "Send me the quarterly numbers", OWNER)
    draft = await clarify.cancel(session, draft.id, OWNER)
    assert draft.status == "abandoned"
    with pytest.raises(clarify.DraftFinished):
        await clarify.confirm(session, draft.id, OWNER)
    assert await clarify.list_active(session, OWNER) == []


async def test_expired_draft_is_not_found_and_swept(session):
    with _classifier(_asking(), _asking()):
        stale = await clarify.start(session, "Send me the quarterly numbers", OWNER)
        ancient = await clarify.start(session, "Send me the yearly numbers", OWNER)
    now = datetime.now(timezone.utc)
    stale.expires_at = now - timedelta(minutes=1)
    ancient.expires_at = now - timedelta(hours=25)
    ancient.status = "abandoned"
    await session.commit()

    with pytest.raises(clarify.DraftNotFound):
        await clarify.get(session, stale.id, OWNER)
    with pytest.raises(clarify.DraftNotFound):
        await clarify.answer(session, stale.id, OWNER, {"source": "x"})
    assert await clarify.list_active(session, OWNER) == []

    assert await clarify.sweep_expired_drafts(session) == (1, 1)
    session.expire_all()
    remaining = (await session.execute(select(TaskSpecDraft))).scalars().all()
    assert [(d.id, d.status) for d in remaining] == [(stale.id, "abandoned")]


async def test_list_active_is_owner_scoped_newest_first(session):
    with _classifier(_asking(), _ready(), _asking()):
        first = await clarify.start(session, "one", OWNER)
        second = await clarify.start(session, "two", OWNER)
        await clarify.start(session, "three", "bob@example.com")
    first.created_at = datetime.now(timezone.utc) - timedelta(minutes=5)
    await session.commit()
    assert [d.id for d in await clarify.list_active(session, OWNER)] == [second.id, first.id]


def test_owner_identity_prefers_email():
    assert clarify.owner_identity({"email": "a@b.c", "sub": "123"}) == "a@b.c"
    assert clarify.owner_identity({"sub": "123"}) == "123"


async def test_draft_sweeper_sweeps_on_start_and_survives_errors(db_session):
    import asyncio

    _, session_maker = db_session
    calls = []

    async def sweep(session):
        calls.append(session)
        if len(calls) == 1:
            raise RuntimeError("boom")
        return (0, 0)

    with patch("clarify.sweep_expired_drafts", side_effect=sweep):
        runner = asyncio.create_task(clarify.run_draft_sweeper(session_maker, interval=0))
        while len(calls) < 2:
            await asyncio.sleep(0)
        runner.cancel()
    assert len(calls) >= 2
