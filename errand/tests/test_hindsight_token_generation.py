"""errand mints the Hindsight bearer when nobody else does.

Hindsight's REST API and MCP endpoint are open unless it is started with the
API-key tenant extension, which needs a shared secret. Leaving that secret for
the operator to invent means the default deployment is an unauthenticated
memory service, because the person who would have to invent it is the person
least likely to know it matters.

The risk in generating it is the opposite failure: silently replacing a token an
operator did configure, which breaks memory for every task with a 401 that
points nowhere. So the tests below spend most of their attention on the cases
where generation must *not* happen.
"""

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from models import Setting
from settings_registry import ensure_hindsight_token, mask_sensitive_value, resolve_settings
from tests.conftest import _create_tables


@pytest.fixture()
async def session():
    """A throwaway in-memory database, matching test_settings_registry.py's style."""
    engine = create_async_engine("sqlite+aiosqlite://", echo=False)
    await _create_tables(engine)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as s:
        yield s
    await engine.dispose()


async def stored_token(session) -> str | None:
    result = await session.execute(select(Setting).where(Setting.key == "hindsight_token"))
    row = result.scalars().first()
    return row.value if row is not None else None


@pytest.fixture
def no_hindsight_env(monkeypatch):
    """Neither variable set — the ordinary self-hosted compose case."""
    monkeypatch.delenv("HINDSIGHT_TOKEN", raising=False)
    monkeypatch.delenv("HINDSIGHT_URL", raising=False)


class TestGeneratesWhenNothingIsConfigured:
    async def test_generates_and_persists_a_token(self, session, no_hindsight_env):
        session.add(Setting(key="hindsight_url", value="http://hindsight:8888"))
        await session.commit()

        token = await ensure_hindsight_token(session)

        assert token
        assert await stored_token(session) == token

    async def test_generated_token_is_long_and_random(self, session, no_hindsight_env):
        """A bearer worth having: `secrets.token_hex(32)` is 64 hex characters."""
        session.add(Setting(key="hindsight_url", value="http://hindsight:8888"))
        await session.commit()

        token = await ensure_hindsight_token(session)

        assert len(token) == 64
        assert all(c in "0123456789abcdef" for c in token)

    async def test_fills_an_existing_but_empty_row(self, session, no_hindsight_env):
        """An empty setting means unset, not configured-as-empty."""
        session.add(Setting(key="hindsight_url", value="http://hindsight:8888"))
        session.add(Setting(key="hindsight_token", value=""))
        await session.commit()

        token = await ensure_hindsight_token(session)

        assert token
        rows = (await session.execute(
            select(Setting).where(Setting.key == "hindsight_token")
        )).scalars().all()
        assert len(rows) == 1, "filled the existing row rather than adding a second"


class TestNeverOverwrites:
    async def test_an_operator_supplied_setting_is_left_alone(self, session, no_hindsight_env):
        session.add(Setting(key="hindsight_url", value="http://hindsight:8888"))
        session.add(Setting(key="hindsight_token", value="operator-chose-this"))
        await session.commit()

        token = await ensure_hindsight_token(session)

        assert token == "operator-chose-this"
        assert await stored_token(session) == "operator-chose-this"

    async def test_env_var_wins_and_nothing_is_written(self, session, monkeypatch):
        monkeypatch.delenv("HINDSIGHT_URL", raising=False)
        monkeypatch.setenv("HINDSIGHT_TOKEN", "from-the-environment")
        session.add(Setting(key="hindsight_url", value="http://hindsight:8888"))
        await session.commit()

        token = await ensure_hindsight_token(session)

        assert token == "from-the-environment"
        assert await stored_token(session) is None, (
            "an env-sourced token must not be copied into the database, or unsetting "
            "the variable would silently leave the old value in force"
        )

    async def test_generation_is_idempotent_across_restarts(self, session, no_hindsight_env):
        """Second call is a restart: the persisted token is reused, not replaced."""
        session.add(Setting(key="hindsight_url", value="http://hindsight:8888"))
        await session.commit()

        first = await ensure_hindsight_token(session)
        second = await ensure_hindsight_token(session)
        third = await ensure_hindsight_token(session)

        assert first == second == third
        assert await stored_token(session) == first


class TestOnlyWhenThereIsSomethingToAuthenticateTo:
    async def test_no_url_means_no_token(self, session, no_hindsight_env):
        assert await ensure_hindsight_token(session) is None
        assert await stored_token(session) is None

    async def test_url_from_the_environment_is_enough(self, session, monkeypatch):
        monkeypatch.delenv("HINDSIGHT_TOKEN", raising=False)
        monkeypatch.setenv("HINDSIGHT_URL", "http://hindsight:8888")

        token = await ensure_hindsight_token(session)

        assert token
        assert await stored_token(session) == token


class TestMasking:
    async def test_generated_token_is_masked_by_the_settings_api(self, session, no_hindsight_env):
        session.add(Setting(key="hindsight_url", value="http://hindsight:8888"))
        await session.commit()
        token = await ensure_hindsight_token(session)

        resolved = await resolve_settings(session)
        entry = resolved["hindsight_token"]

        assert entry["sensitive"] is True
        assert entry["value"] == mask_sensitive_value(token)
        assert entry["value"] != token
        assert token not in str(resolved), "the full token must not appear anywhere in the payload"

    async def test_database_sourced_token_is_masked_too(self, session, no_hindsight_env):
        """Masking is per-key, not per-source: a configured token reads back masked as well."""
        session.add(Setting(key="hindsight_token", value="operator-chose-this"))
        await session.commit()

        entry = (await resolve_settings(session))["hindsight_token"]

        assert entry["source"] == "database"
        assert entry["value"] == mask_sensitive_value("operator-chose-this")

    async def test_an_unset_token_reads_back_empty_not_masked(self, session, no_hindsight_env):
        """"Not configured" must stay distinguishable from "configured but hidden".

        `mask_sensitive_value("")` returns "****", so masking unconditionally
        would make an unset key look exactly like a set one — to an operator
        reading the settings page, and to any UI branching on emptiness.
        """
        entry = (await resolve_settings(session))["hindsight_token"]

        assert entry["source"] == "default"
        assert entry["value"] == "", f"unset token read back as {entry['value']!r}"

    async def test_masking_does_not_leak_into_other_sensitive_keys(self, session):
        """`mcp_api_key` is displayed on purpose — the settings UI exists to show it."""
        session.add(Setting(key="mcp_api_key", value="0123456789abcdef"))
        await session.commit()

        entry = (await resolve_settings(session))["mcp_api_key"]

        assert entry["value"] == "0123456789abcdef"


class TestGeneratedTokenIsNotLogged:
    async def test_the_value_never_reaches_our_own_log(self, session, no_hindsight_env, caplog):
        """The "Generated ..." line says that it happened, never what was generated.

        Scoped to the `settings_registry` logger deliberately. At DEBUG the
        SQLAlchemy/aiosqlite driver echoes the INSERT statement with its bound
        parameters, which would contain the token — but that is true of every
        secret in the settings table (`mcp_api_key`, `jwt_signing_secret`), is a
        property of turning on SQL echo rather than of this code, and asserting
        against it here would pin behaviour this module does not own.
        """
        session.add(Setting(key="hindsight_url", value="http://hindsight:8888"))
        await session.commit()

        with caplog.at_level("DEBUG", logger="settings_registry"):
            caplog.clear()
            token = await ensure_hindsight_token(session)

        ours = [r for r in caplog.records if r.name == "settings_registry"]
        assert ours, "generation should say that it happened"
        assert all(token not in r.getMessage() for r in ours)
        assert all(token not in str(r.args or ()) for r in ours)
