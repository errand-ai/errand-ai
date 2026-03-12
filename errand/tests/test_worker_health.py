"""Tests for the worker health HTTP endpoint."""
import urllib.request
from unittest.mock import patch

from worker import start_health_server


def test_health_ok():
    server = start_health_server(port=0)  # OS-assigned port
    port = server.server_address[1]
    try:
        resp = urllib.request.urlopen(f"http://127.0.0.1:{port}/health")
        assert resp.status == 200
        assert b'"status": "ok"' in resp.read()
    finally:
        server.shutdown()


def test_health_shutting_down():
    server = start_health_server(port=0)
    port = server.server_address[1]
    try:
        with patch("worker.shutdown_requested", True):
            try:
                urllib.request.urlopen(f"http://127.0.0.1:{port}/health")
                assert False, "Expected HTTP error"
            except urllib.error.HTTPError as e:
                assert e.code == 503
                assert b'"status": "shutting_down"' in e.read()
    finally:
        server.shutdown()


def test_health_404_on_unknown_path():
    server = start_health_server(port=0)
    port = server.server_address[1]
    try:
        try:
            urllib.request.urlopen(f"http://127.0.0.1:{port}/unknown")
            assert False, "Expected HTTP error"
        except urllib.error.HTTPError as e:
            assert e.code == 404
    finally:
        server.shutdown()
