"""repair runner_logs stored as a Python bytes repr

Revision ID: 031
Revises: 030

On Kubernetes, `KubernetesRuntime.result()` read pod logs through the client's
preloaded `str` deserialisation, which returns `str(bytes)` when the body is not
valid JSON — as pod logs never are. Affected rows hold the Python repr
(`b'...\\n...'`) in which line breaks are the two-character sequence backslash-n,
so consumers splitting on newlines get a single unparseable line.

The writer is fixed in the same change; this repairs rows already stored.

Detection is deliberately conjunctive. A value is repaired only when it starts
with a bytes-literal prefix, ends with the matching quote, contains no real line
breaks, and evaluates to a `bytes` object. Anything failing any condition — most
importantly a repr truncated past its closing quote by `truncate_output` — is
left byte-for-byte alone. A log that cannot be recovered cleanly is better left
visibly wrong than silently mangled further.
"""

import ast
import logging

from alembic import op
import sqlalchemy as sa

revision = "031"
down_revision = "030"

logger = logging.getLogger("alembic.runtime.migration")


def _decode_bytes_repr(value: str) -> str | None:
    """Return the decoded text of a bytes repr, or None if it is not safely one.

    Every condition must hold. Returning None means "leave this row alone", which
    is always the safe answer: the cost of skipping a repairable row is a log that
    still renders raw, while the cost of rewriting a row we misread is data loss.
    """
    if not isinstance(value, str) or len(value) < 3:
        return None
    # Must open with a bytes literal prefix and close with the matching quote.
    if value[0] != "b" or value[1] not in ("'", '"'):
        return None
    if not value.endswith(value[1]):
        return None
    # A genuine bytes repr has no real line breaks — its newlines are escaped.
    # This is what distinguishes it from an ordinary log that merely starts "b'".
    if "\n" in value or "\r" in value:
        return None
    try:
        # literal_eval, never eval: it evaluates literals only and executes nothing.
        decoded = ast.literal_eval(value)
    except (ValueError, SyntaxError, MemoryError, RecursionError):
        return None
    if not isinstance(decoded, bytes):
        return None
    try:
        return decoded.decode("utf-8", errors="replace")
    except Exception:
        return None


def upgrade() -> None:
    conn = op.get_bind()
    rows = conn.execute(
        sa.text(
            # Narrow the scan to plausible candidates; _decode_bytes_repr still
            # re-checks every condition, so this is an optimisation, not the guard.
            "SELECT id, runner_logs FROM tasks "
            "WHERE runner_logs IS NOT NULL "
            "AND (runner_logs LIKE 'b''%' OR runner_logs LIKE 'b\"%')"
        )
    ).fetchall()

    repaired = 0
    skipped = 0
    for task_id, logs in rows:
        decoded = _decode_bytes_repr(logs)
        if decoded is None:
            skipped += 1
            continue
        conn.execute(
            sa.text("UPDATE tasks SET runner_logs = :logs WHERE id = :id"),
            {"logs": decoded, "id": task_id},
        )
        repaired += 1

    # Counts, so the result can be compared against what was measured before the
    # deploy rather than assumed. A non-zero skip count is worth looking at.
    logger.info(
        "runner_logs bytes-repr repair: %d candidate(s), %d repaired, %d skipped",
        len(rows), repaired, skipped,
    )


def downgrade() -> None:
    # Deliberately a no-op. Re-encoding repaired logs back into a bytes repr would
    # restore corrupt data, which has no value and would undo the fix for anyone
    # who rolled back one version. The repaired rows are correct under both.
    pass
