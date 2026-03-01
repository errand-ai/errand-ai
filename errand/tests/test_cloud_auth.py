"""Tests for cloud auth module (PKCE, state management, token exchange)."""
import base64
import hashlib

import pytest

from cloud_auth import (
    consume_state,
    generate_pkce,
    store_state,
    _oauth_states,
)


class TestPKCE:
    def test_generates_code_verifier_and_challenge(self):
        verifier, challenge = generate_pkce()
        assert len(verifier) > 40  # URL-safe base64 of 64 bytes
        assert len(challenge) > 20

    def test_challenge_matches_s256_of_verifier(self):
        verifier, challenge = generate_pkce()
        expected_digest = hashlib.sha256(verifier.encode("ascii")).digest()
        expected_challenge = base64.urlsafe_b64encode(expected_digest).rstrip(b"=").decode("ascii")
        assert challenge == expected_challenge

    def test_generates_unique_values(self):
        v1, c1 = generate_pkce()
        v2, c2 = generate_pkce()
        assert v1 != v2
        assert c1 != c2


class TestStateManagement:
    def setup_method(self):
        _oauth_states.clear()

    def test_store_and_consume_state(self):
        store_state("test-state", "test-verifier")
        result = consume_state("test-state")
        assert result == "test-verifier"

    def test_consume_removes_state(self):
        store_state("test-state", "test-verifier")
        consume_state("test-state")
        result = consume_state("test-state")
        assert result is None

    def test_invalid_state_returns_none(self):
        result = consume_state("nonexistent")
        assert result is None

    def test_expired_state_returns_none(self):
        import time
        _oauth_states["expired"] = {
            "code_verifier": "old-verifier",
            "created_at": time.time() - 700,  # > 600s TTL
        }
        result = consume_state("expired")
        assert result is None
