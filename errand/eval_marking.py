"""Server-side eval-task marking.

A task is an *eval* task when the profile it runs under is an eval clone — by
convention, a profile whose name starts with ``eval--`` (see the LLM eval
framework). The ``tasks.is_eval`` flag is set here at creation time, never by the
client, and the board/list APIs exclude flagged tasks by default. Persisting the
flag (rather than deriving it from the profile at query time) means it survives
the profile's later deletion (``tasks.profile_id`` is ``ON DELETE SET NULL``).
"""

from sqlalchemy import select

from models import TaskProfile

EVAL_PROFILE_PREFIX = "eval--"


def is_eval_profile_name(name: str | None) -> bool:
    """True if a profile name marks its tasks as eval tasks."""
    return bool(name and name.startswith(EVAL_PROFILE_PREFIX))


async def resolve_is_eval(session, profile_id) -> bool:
    """Return whether a task under ``profile_id`` should be flagged is_eval.

    Resolves the profile's name from its id so every creation path (explicit
    profile, LLM-suggested profile, or none) is handled uniformly. A null profile
    is never an eval task.
    """
    if profile_id is None:
        return False
    name = (
        await session.execute(select(TaskProfile.name).where(TaskProfile.id == profile_id))
    ).scalar_one_or_none()
    return is_eval_profile_name(name)
