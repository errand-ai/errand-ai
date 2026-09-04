"""Alembic owns `public`, and nothing else.

Hindsight now lives in a `hindsight` schema inside errand's own database rather
than in a second database (see the `local-dev-environment` spec). The two share
a connection string, so the only thing keeping them apart is that each stays in
its own schema. Nothing enforces that at the database level — the errand role
can write to both — so it is enforced here instead.

The check is over migration *source* rather than over a migrated database on
purpose: it constrains every future migration, including ones written long after
anybody remembers why the boundary exists, and it fails at unit-test time rather
than after a deploy has already written to the wrong schema.
"""
import ast
import pathlib
import re

import pytest

VERSIONS_DIR = pathlib.Path(__file__).resolve().parents[1] / "alembic" / "versions"
ENV_PY = pathlib.Path(__file__).resolve().parents[1] / "alembic" / "env.py"

# `None` is what SQLAlchemy means by "the connection's default schema", which for
# errand is `public`. An explicit "public" is equally fine.
ALLOWED_SCHEMAS = {None, "public"}

# Raw-SQL escapes from the AST check. `op.execute("...")` takes a string, so a
# migration can reach another schema without ever passing `schema=`.
RAW_SQL_PATTERNS = (
    re.compile(r"\bCREATE\s+SCHEMA\b", re.IGNORECASE),
    re.compile(r"\bDROP\s+SCHEMA\b", re.IGNORECASE),
    re.compile(r"\bSET\s+search_path\b", re.IGNORECASE),
    re.compile(r"\bCREATE\s+DATABASE\b", re.IGNORECASE),
    # Any schema-qualified reference to Hindsight's tables.
    re.compile(r"\bhindsight\s*\.", re.IGNORECASE),
)


def migration_files() -> list[pathlib.Path]:
    return sorted(p for p in VERSIONS_DIR.glob("*.py") if p.name != "__init__.py")


def test_there_are_migrations_to_check():
    """Guard against the glob silently matching nothing and the suite passing empty."""
    assert len(migration_files()) > 0


@pytest.mark.parametrize("path", migration_files(), ids=lambda p: p.name)
def test_migration_declares_no_foreign_schema(path: pathlib.Path):
    """No `schema=` keyword anywhere in a migration names a schema but `public`."""
    tree = ast.parse(path.read_text(), filename=str(path))

    offenders = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        for kw in node.keywords:
            if kw.arg != "schema":
                continue
            value = kw.value.value if isinstance(kw.value, ast.Constant) else "<not a literal>"
            if value not in ALLOWED_SCHEMAS:
                offenders.append(f"line {kw.value.lineno}: schema={value!r}")

    assert not offenders, (
        f"{path.name} targets a schema other than 'public': {'; '.join(offenders)}. "
        "Alembic owns 'public'; the 'hindsight' schema belongs to Hindsight and is "
        "migrated by Hindsight."
    )


@pytest.mark.parametrize("path", migration_files(), ids=lambda p: p.name)
def test_migration_has_no_schema_crossing_raw_sql(path: pathlib.Path):
    """No raw SQL creates, drops, or switches into another schema or database."""
    source = path.read_text()
    hits = [pattern.pattern for pattern in RAW_SQL_PATTERNS if pattern.search(source)]
    assert not hits, (
        f"{path.name} contains raw SQL matching {hits}. Migrations must stay inside "
        "the connection's default schema; creating schemas or databases, or moving "
        "the search_path, crosses the boundary that keeps errand and Hindsight apart "
        "in one database."
    )


def test_alembic_env_does_not_widen_the_schema_scope():
    """`env.py` must not opt into multi-schema autogeneration or relocate the version table.

    `include_schemas=True` would make autogenerate reflect — and offer to drop —
    Hindsight's tables. `version_table_schema` would move alembic's own bookkeeping
    out of `public`.
    """
    source = ENV_PY.read_text()
    for forbidden in ("include_schemas", "version_table_schema"):
        assert forbidden not in source, (
            f"alembic/env.py sets {forbidden}, which takes alembic outside the "
            "'public' schema it owns."
        )
