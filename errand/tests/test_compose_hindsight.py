"""The Hindsight half of the compose contract.

Every property here was a defect that shipped, or would have:

  * `deploy/docker-compose.yml` mounted a named volume at
    /home/hindsight/.cache with no ownership step, so a first run with empty
    volumes died on `PermissionError: /home/hindsight/.cache/huggingface`.
    `testing/` had the step but the two files drifted independently.
  * Both files published the Control Plane on 9999 unconditionally — an expert
    tool with unauthenticated read/write access to every memory, exposed by
    default to users who will never open it.
  * The bearer errand sends and the bearer Hindsight expects are separate
    environment variables in separate services. If they drift, nothing fails
    loudly: memory calls just come back 401, mid-task.

These are parsed from the compose YAML rather than exercised against a running
stack, so they run in CI with no Docker. That bounds what they can prove — a
service that starts is not in scope — but the failures above are all visible in
the file, and all of them are the kind that reappear when someone edits one
compose file and not the other.
"""

from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
COMPOSE_FILES = [
    REPO_ROOT / "deploy" / "docker-compose.yml",
    REPO_ROOT / "testing" / "docker-compose.yml",
]

# The compose profile the Control Plane must sit behind.
MEMORY_UI_PROFILE = "memory-ui"
CONTROL_PLANE_PORT = "9999"


def load(path: Path) -> dict:
    return yaml.safe_load(path.read_text())


def services(path: Path) -> dict:
    return load(path).get("services", {})


def hindsight_service(path: Path) -> dict:
    """The Hindsight API service itself — not the init, build or Control Plane ones."""
    return services(path)["hindsight"]


def env_of(service: dict) -> dict:
    """Compose allows both mapping and `KEY=value` list forms; normalise to a dict."""
    raw = service.get("environment", {})
    if isinstance(raw, dict):
        return {k: ("" if v is None else str(v)) for k, v in raw.items()}
    out = {}
    for item in raw:
        key, _, value = str(item).partition("=")
        out[key] = value
    return out


def volume_mount_targets(service: dict) -> list[str]:
    """Container-side paths of `source:target` mounts, ignoring bind-mounted files."""
    targets = []
    for mount in service.get("volumes", []) or []:
        if isinstance(mount, dict):
            target = mount.get("target")
            if target:
                targets.append(target)
            continue
        parts = str(mount).split(":")
        if len(parts) >= 2:
            targets.append(parts[1])
    return targets


def compose_id(path: Path) -> str:
    return f"{path.parent.name}/{path.name}"


pytestmark = pytest.mark.parametrize("path", COMPOSE_FILES, ids=compose_id)


class TestVolumeOwnership:
    """The mounted directories must be writable by uid 1000 before Hindsight starts."""

    def test_every_hindsight_mount_is_chowned_by_an_init_service(self, path: Path):
        mounts = volume_mount_targets(hindsight_service(path))
        assert mounts, f"{compose_id(path)}: hindsight mounts no volumes — has the layout changed?"

        init = services(path)["hindsight-init"]
        command = init.get("command", "")
        if isinstance(command, list):
            command = " ".join(str(part) for part in command)

        assert init.get("user") == "root", (
            f"{compose_id(path)}: hindsight-init must run as root to chown a "
            "root-owned empty volume"
        )

        uncovered = [m for m in mounts if m not in command]
        assert not uncovered, (
            f"{compose_id(path)}: hindsight mounts {uncovered} but hindsight-init "
            f"chowns only {command!r}. A path mounted into Hindsight and not "
            "chowned is a first-run PermissionError."
        )

    def test_hindsight_waits_for_the_ownership_step(self, path: Path):
        depends = hindsight_service(path).get("depends_on", {})
        assert "hindsight-init" in depends, (
            f"{compose_id(path)}: hindsight does not depend on hindsight-init, so "
            "the chown may not have run when it starts"
        )
        assert depends["hindsight-init"]["condition"] == "service_completed_successfully"


class TestSingleDatabase:
    """Memory lives in a schema of errand's database, not a database of its own."""

    def test_hindsight_uses_the_errand_database(self, path: Path):
        errand_url = env_of(services(path)["errand"])["DATABASE_URL"]
        hindsight_url = env_of(hindsight_service(path))["HINDSIGHT_API_DATABASE_URL"]
        errand_db = errand_url.rsplit("/", 1)[-1]
        hindsight_db = hindsight_url.rsplit("/", 1)[-1]
        assert hindsight_db == errand_db, (
            f"{compose_id(path)}: hindsight points at database {hindsight_db!r} but "
            f"errand uses {errand_db!r}; they are meant to share one database."
        )

    def test_hindsight_is_confined_to_its_own_schema(self, path: Path):
        assert env_of(hindsight_service(path))["HINDSIGHT_API_DATABASE_SCHEMA"] == "hindsight"

    def test_hindsight_pins_a_stable_worker_id(self, path: Path):
        """Upstream warns that a hostname-derived worker id can strand claimed work."""
        assert env_of(hindsight_service(path)).get("HINDSIGHT_API_WORKER_ID")


class TestControlPlaneIsOptIn:
    def test_control_plane_sits_behind_the_memory_ui_profile(self, path: Path):
        cp = services(path)["hindsight-control-plane"]
        assert MEMORY_UI_PROFILE in cp.get("profiles", []), (
            f"{compose_id(path)}: the Control Plane must be behind the "
            f"{MEMORY_UI_PROFILE!r} profile, or a plain `docker compose up` starts it"
        )

    def test_no_unprofiled_service_publishes_the_control_plane_port(self, path: Path):
        offenders = [
            name
            for name, service in services(path).items()
            if not service.get("profiles")
            and any(CONTROL_PLANE_PORT in str(p).split(":") for p in service.get("ports", []) or [])
        ]
        assert not offenders, (
            f"{compose_id(path)}: {offenders} publish port {CONTROL_PLANE_PORT} without "
            "a profile, so a default bring-up exposes the Control Plane"
        )

    def test_control_plane_is_pointed_at_the_api(self, path: Path):
        env = env_of(services(path)["hindsight-control-plane"])
        assert env["HINDSIGHT_CP_DATAPLANE_API_URL"] == "http://hindsight:8888"


class TestBearerWiring:
    """errand's bearer and Hindsight's expected key must be the same expression."""

    def test_hindsight_enables_the_api_key_tenant_extension(self, path: Path):
        env = env_of(hindsight_service(path))
        assert env["HINDSIGHT_API_TENANT_EXTENSION"].endswith(":ApiKeyTenantExtension"), (
            f"{compose_id(path)}: without a tenant extension Hindsight's REST API and "
            "MCP endpoint are both open to anything on the network"
        )

    def test_errand_and_hindsight_agree_on_the_token(self, path: Path):
        errand_token = env_of(services(path)["errand"])["HINDSIGHT_TOKEN"]
        hindsight_key = env_of(hindsight_service(path))["HINDSIGHT_API_TENANT_API_KEY"]
        assert errand_token == hindsight_key, (
            f"{compose_id(path)}: errand sends {errand_token!r} but Hindsight expects "
            f"{hindsight_key!r}. A mismatch surfaces as a 401 mid-task, not at start-up."
        )

    def test_the_token_is_never_empty(self, path: Path):
        """An unset key makes ApiKeyTenantExtension raise at start-up, not fail open."""
        key = env_of(hindsight_service(path))["HINDSIGHT_API_TENANT_API_KEY"]
        assert not key.endswith(":-}"), (
            f"{compose_id(path)}: {key!r} defaults to empty; ApiKeyTenantExtension "
            "raises ValueError on an empty key, so Hindsight would not start"
        )

    def test_control_plane_authenticates_to_the_api(self, path: Path):
        """Enabling the extension closes REST too, so the Control Plane needs the bearer."""
        cp = env_of(services(path)["hindsight-control-plane"])
        hindsight_key = env_of(hindsight_service(path))["HINDSIGHT_API_TENANT_API_KEY"]
        assert cp["HINDSIGHT_CP_DATAPLANE_API_KEY"] == hindsight_key, (
            f"{compose_id(path)}: the Control Plane would 401 on every call"
        )

    def test_control_plane_has_its_own_login(self, path: Path):
        cp = env_of(services(path)["hindsight-control-plane"])
        assert cp.get("HINDSIGHT_CP_ACCESS_KEY"), (
            f"{compose_id(path)}: without HINDSIGHT_CP_ACCESS_KEY the Control Plane has "
            "no login at all, on a UI with full read/write access to every memory"
        )


def test_init_script_creates_no_hindsight_database(path: Path):
    """The database init script mounted by this compose file must not create a second database.

    Comments are stripped first: the script explains *why* there is no
    `CREATE DATABASE hindsight`, and a substring search over the raw file would
    match that explanation.
    """
    scripts = []
    for name, service in services(path).items():
        for mount in service.get("volumes", []) or []:
            if not isinstance(mount, str) or "docker-entrypoint-initdb.d" not in mount:
                continue
            source = mount.split(":")[0]
            scripts.append((path.parent / source).resolve())

    assert scripts, (
        f"{compose_id(path)}: no script is mounted into docker-entrypoint-initdb.d, so "
        "nothing installs the `vector` extension before Hindsight first connects"
    )

    for script in scripts:
        sql = "\n".join(
            line for line in script.read_text().splitlines() if not line.lstrip().startswith("#")
        )
        assert "CREATE DATABASE hindsight" not in sql, (
            f"{script.name}: Hindsight shares errand's database now; a second one is "
            "left orphaned and, on Kubernetes, cannot be created by errand's chart"
        )
        for extension in ("vector", "pg_trgm"):
            assert f"CREATE EXTENSION IF NOT EXISTS {extension};" in sql, (
                f"{script.name}: `{extension}` must be created here, in the default "
                "(public) schema. Hindsight resolves against a search_path carrying "
                "`public`, so an extension anywhere else is invisible to it. For "
                "`pg_trgm` this is load-bearing: left to itself Hindsight creates it "
                "in its own tenant schema, every retain then fails entity resolution "
                "with `operator does not exist: text % text`, and because the MCP "
                "`retain` call still returns \"accepted\" the only symptom is that "
                "memory silently never appears."
            )
            assert f"EXISTS {extension} SCHEMA" not in sql, (
                f"{script.name}: do not give `{extension}` an explicit SCHEMA — "
                "CREATE EXTENSION IF NOT EXISTS matches on the database rather than "
                "the schema, so a wrong placement here silently pre-empts Hindsight's "
                "own create and cannot be recovered without an ALTER EXTENSION."
            )
