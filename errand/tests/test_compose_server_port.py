"""The host port errand publishes on must be overridable.

Port 8000 is vLLM's default and one of the candidate ports local AI detection
probes. A user running an OpenAI-compatible server there — exactly the user
local detection was written for — cannot bring up the shipped compose beside
it: the publish fails, or worse, shadows the runtime the scan was meant to
find. This bit during verification of `local-ai-provider-detection`, where the
host port was shadowed and errand's own API became unreachable from the host.

Dropping 8000 from the candidate table would be worse. The collision is
errand's to yield.

Parsed from the YAML rather than exercised against a running stack, for the
same reason as `test_compose_host_gateway.py`: the two files have drifted
before.
"""

from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
COMPOSE_FILES = [
    REPO_ROOT / "deploy" / "docker-compose.yml",
    REPO_ROOT / "testing" / "docker-compose.yml",
]

PUBLISHED_PORT = "${ERRAND_PORT:-8000}:8000"


def errand_ports(path: Path) -> list:
    services = yaml.safe_load(path.read_text()).get("services", {})
    assert "errand" in services, f"errand missing from {path}"
    return services["errand"].get("ports") or []


@pytest.mark.parametrize("compose_file", COMPOSE_FILES, ids=lambda p: p.parent.name)
def test_host_port_is_overridable(compose_file: Path):
    assert PUBLISHED_PORT in errand_ports(compose_file), (
        f"{compose_file} does not publish errand through an overridable variable"
    )


@pytest.mark.parametrize("compose_file", COMPOSE_FILES, ids=lambda p: p.parent.name)
def test_the_default_is_unchanged(compose_file: Path):
    """No existing deployment moves — only the ability to override is new."""
    published = next(p for p in errand_ports(compose_file) if p.endswith(":8000"))
    host_side = published.rsplit(":", 1)[0]

    assert host_side.endswith(":-8000}"), f"{compose_file} defaults to something other than 8000"


@pytest.mark.parametrize("compose_file", COMPOSE_FILES, ids=lambda p: p.parent.name)
def test_the_container_port_is_not_overridable(compose_file: Path):
    """Only the host side moves. The healthcheck and every in-network URL
    address the container on 8000, so a variable there would break them."""
    published = next(p for p in errand_ports(compose_file) if p.endswith(":8000"))

    assert published.rsplit(":", 1)[1] == "8000"
