"""Unit tests for host_gateway.py — the host gateway address and detection availability."""
from unittest.mock import patch

from host_gateway import (
    HOST_GATEWAY_DEFAULT,
    get_host_gateway_address,
    is_local_detection_available,
)


class TestGetHostGatewayAddress:
    def test_defaults_when_unset(self):
        """An unset HOST_GATEWAY_ADDRESS yields the Docker Desktop default."""
        with patch.dict("os.environ", {}, clear=True):
            assert get_host_gateway_address() == HOST_GATEWAY_DEFAULT
            assert HOST_GATEWAY_DEFAULT == "host.docker.internal"

    def test_explicit_address_is_used(self):
        """A runtime-specific address (e.g. an Apple vmnet gateway) is used verbatim."""
        with patch.dict("os.environ", {"HOST_GATEWAY_ADDRESS": "192.168.64.1"}, clear=True):
            assert get_host_gateway_address() == "192.168.64.1"

    def test_explicitly_empty_disables(self):
        """An explicitly empty value means 'no host is addressable'."""
        with patch.dict("os.environ", {"HOST_GATEWAY_ADDRESS": ""}, clear=True):
            assert get_host_gateway_address() is None

    def test_whitespace_only_disables(self):
        """Whitespace is not an address."""
        with patch.dict("os.environ", {"HOST_GATEWAY_ADDRESS": "   "}, clear=True):
            assert get_host_gateway_address() is None

    def test_surrounding_whitespace_stripped(self):
        with patch.dict("os.environ", {"HOST_GATEWAY_ADDRESS": " host.docker.internal "}, clear=True):
            assert get_host_gateway_address() == "host.docker.internal"


class TestIsLocalDetectionAvailable:
    def test_available_by_default(self):
        with patch.dict("os.environ", {}, clear=True):
            assert is_local_detection_available() is True

    def test_unavailable_when_address_empty(self):
        with patch.dict("os.environ", {"HOST_GATEWAY_ADDRESS": ""}, clear=True):
            assert is_local_detection_available() is False

    def test_unavailable_on_kubernetes(self):
        """There is no addressable host on Kubernetes, whatever the address says."""
        with patch.dict(
            "os.environ",
            {"CONTAINER_RUNTIME": "kubernetes", "HOST_GATEWAY_ADDRESS": "host.docker.internal"},
            clear=True,
        ):
            assert is_local_detection_available() is False

    def test_available_on_docker_runtime(self):
        with patch.dict("os.environ", {"CONTAINER_RUNTIME": "docker"}, clear=True):
            assert is_local_detection_available() is True

    def test_available_on_apple_runtime(self):
        """The desktop app supplies a vmnet gateway address; detection stays available."""
        with patch.dict(
            "os.environ",
            {"CONTAINER_RUNTIME": "apple", "HOST_GATEWAY_ADDRESS": "192.168.64.1"},
            clear=True,
        ):
            assert is_local_detection_available() is True
