"""The address by which this server reaches services on the container host.

errand-server cannot reliably derive its own runtime topology: Docker resolves
the host as ``host.docker.internal``, Apple Containerization uses a vmnet
gateway address, and a Kubernetes pod has no addressable host at all. So the
address is injected as a deployment fact rather than inferred, and everything
that needs to reach a host-run service — local AI detection, and the host entry
added to task containers — reads it from here.
"""

import os

HOST_GATEWAY_DEFAULT = "host.docker.internal"


def get_host_gateway_address() -> str | None:
    """Return the configured host gateway address, or None when there is none.

    An unset ``HOST_GATEWAY_ADDRESS`` yields the Docker Desktop default, which
    both shipped compose files map to the real host via ``extra_hosts``. An
    explicitly empty value is a deliberate statement that no host is
    addressable, and yields None.
    """
    raw = os.environ.get("HOST_GATEWAY_ADDRESS")
    if raw is None:
        return HOST_GATEWAY_DEFAULT
    address = raw.strip()
    return address or None


def is_local_detection_available() -> bool:
    """Whether local AI runtimes on the container host can be probed at all.

    False when no gateway address is configured, and always false on
    Kubernetes, where there is no host to detect.
    """
    if os.environ.get("CONTAINER_RUNTIME", "docker") == "kubernetes":
        return False
    return get_host_gateway_address() is not None
