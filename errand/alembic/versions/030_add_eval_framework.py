"""add eval framework: tasks.is_eval, eval_runs, eval_results

Revision ID: 030
Revises: 029
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision = "030"
down_revision = "029"


def upgrade() -> None:
    # Eval tasks are ordinary tasks run under eval-- profiles; the flag is set
    # server-side at creation and lets the board APIs exclude them by default.
    op.add_column(
        "tasks",
        sa.Column(
            "is_eval",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )

    op.create_table(
        "eval_runs",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("mode", sa.Text(), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("corpus_version", sa.Text(), nullable=False),
        sa.Column("errand_version", sa.Text(), nullable=False),
        sa.Column("judge_model", sa.Text(), nullable=False),
        sa.Column("driver_host", sa.Text(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
    )

    op.create_table(
        "eval_results",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "run_id",
            UUID(as_uuid=True),
            sa.ForeignKey("eval_runs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("workload", sa.Text(), nullable=False),
        sa.Column("model", sa.Text(), nullable=False),
        sa.Column(
            "task_id",
            UUID(as_uuid=True),
            sa.ForeignKey("tasks.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("rep", sa.Integer(), nullable=False),
        sa.Column("verdict", sa.Text(), nullable=False),
        sa.Column("score", sa.Numeric(), nullable=True),
        sa.Column("turns", sa.Integer(), nullable=True),
        sa.Column("recoveries", sa.Integer(), nullable=True),
        sa.Column("error_events", sa.Integer(), nullable=True),
        sa.Column("wall_seconds", sa.Numeric(), nullable=True),
        sa.Column("judge_output", JSONB(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.UniqueConstraint("run_id", "workload", "model", "rep", name="uq_eval_results_cell"),
    )
    op.create_index("ix_eval_results_run_id", "eval_results", ["run_id"])


def downgrade() -> None:
    op.drop_index("ix_eval_results_run_id", table_name="eval_results")
    op.drop_table("eval_results")
    op.drop_table("eval_runs")
    op.drop_column("tasks", "is_eval")
