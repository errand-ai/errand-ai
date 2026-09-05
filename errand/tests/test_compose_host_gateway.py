"""Both compose files must let host-reaching services resolve the host gateway.

A locally detected AI runtime is registered with the base URL that answered the
probe — `http://host.docker.internal:11434/v1`. That URL is stored once and
consumed by errand-server (model listing, title generation), by the memory
service, and by every task container. If any one of those cannot resolve the
name, the failure is a connection error at the point of use, far from the
compose file that omitted the mapping.

Parsed from the YAML rather than exercised against a running stack, for the same
reason as `test_compose_hindsight.py`: the two files have drifted before.
"""

from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
COMPOSE_FILES = [
    REPO_ROOT / "deploy" / "docker-compose.yml",
    REPO_ROOT / "testing" / "docker-compose.yml",
]

# The services that resolve a stored provider base_url themselves. Task
# containers are not here: they are created by DockerRuntime, which adds the
# entry itself (see test_container_runtime.py).
HOST_REACHING_SERVICES = ["errand", "hindsight"]

GATEWAY_ENTRY = "host.docker.internal:host-gateway"


def services(path: Path) -> dict:
    return yaml.safe_load(path.read_text()).get("services", {})


@pytest.mark.parametrize("compose_file", COMPOSE_FILES, ids=lambda p: p.parent.name)
@pytest.mark.parametrize("service_name", HOST_REACHING_SERVICES)
def test_service_declares_host_gateway(compose_file: Path, service_name: str):
    """errand and hindsight can both resolve the host gateway name."""
    service = services(compose_file).get(service_name)
    assert service is not None, f"{service_name} missing from {compose_file}"

    extra_hosts = service.get("extra_hosts")
    assert extra_hosts, f"{service_name} in {compose_file} declares no extra_hosts"
    assert GATEWAY_ENTRY in extra_hosts


@pytest.mark.parametrize("compose_file", COMPOSE_FILES, ids=lambda p: p.parent.name)
def test_uses_host_gateway_token_not_a_hard_coded_address(compose_file: Path):
    """`host-gateway` is resolved by the engine, so one mapping serves Desktop and Linux."""
    for service_name in HOST_REACHING_SERVICES:
        for entry in services(compose_file)[service_name]["extra_hosts"]:
            assert entry.endswith(":host-gateway"), (
                f"{service_name} in {compose_file} hard-codes a host address in {entry!r}; "
                "use the engine's host-gateway token so the mapping works on Linux too"
            )


@pytest.mark.parametrize("compose_file", COMPOSE_FILES, ids=lambda p: p.parent.name)
def test_task_runner_network_is_named(compose_file: Path):
    """Detected providers are refused under host networking, so the network must be named."""
    errand = services(compose_file)["errand"]
    assert errand["environment"].get("TASK_RUNNER_NETWORK"), (
        f"{compose_file} leaves TASK_RUNNER_NETWORK unset, which puts task containers "
        "on host networking and makes locally detected providers unusable"
    )
