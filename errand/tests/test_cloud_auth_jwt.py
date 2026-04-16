"""Tests for cloud-trusted JWT authentication."""
import time
from unittest.mock import MagicMock, patch

import jwt as pyjwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa

import cloud_auth_jwt

# Fixed issuer used across tests; aligned with CLOUD_KEYCLOAK_URL below.
_TEST_ISSUER = "https://keycloak.example.com/realms/errand"


@pytest.fixture(autouse=True)
def _pin_cloud_keycloak_url(monkeypatch):
    """Pin the trusted issuer for every test so validate_cloud_jwt is enabled."""
    monkeypatch.setenv(cloud_auth_jwt.CLOUD_KEYCLOAK_URL_ENV, _TEST_ISSUER)


@pytest.fixture()
def rsa_keypair():
    """Generate an RSA keypair for test JWT signing."""
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    public_key = private_key.public_key()
    return private_key, public_key


def _make_cloud_jwt(private_key, sub="cloud-user", issuer="https://keycloak.example.com/realms/errand", expired=False, **extra_claims):
    """Create a JWT signed with RSA key (simulating Keycloak cloud token)."""
    import time as _time
    now = int(_time.time())
    exp = now - 3600 if expired else now + 3600
    claims = {
        "sub": sub,
        "iss": issuer,
        "iat": now,
        "exp": exp,
        "email": f"{sub}@cloud.example.com",
        "preferred_username": sub,
        **extra_claims,
    }
    return pyjwt.encode(claims, private_key, algorithm="RS256")


def test_validate_cloud_jwt_valid(rsa_keypair):
    """Valid cloud JWT should be accepted."""
    private_key, public_key = rsa_keypair
    token = _make_cloud_jwt(private_key)

    # Mock the JWKS client to return our test key
    mock_jwk = MagicMock()
    mock_jwk.key = public_key

    mock_jwks_client = MagicMock()
    mock_jwks_client.get_signing_key_from_jwt.return_value = mock_jwk

    with patch.object(cloud_auth_jwt, '_ensure_jwks_client', return_value=mock_jwks_client):
        claims = cloud_auth_jwt.validate_cloud_jwt(token)
        assert claims["sub"] == "cloud-user"
        assert claims["iss"] == "https://keycloak.example.com/realms/errand"


def test_validate_cloud_jwt_expired(rsa_keypair):
    """Expired cloud JWT should be rejected."""
    private_key, public_key = rsa_keypair
    token = _make_cloud_jwt(private_key, expired=True)

    mock_jwk = MagicMock()
    mock_jwk.key = public_key

    mock_jwks_client = MagicMock()
    mock_jwks_client.get_signing_key_from_jwt.return_value = mock_jwk

    with patch.object(cloud_auth_jwt, '_ensure_jwks_client', return_value=mock_jwks_client):
        with pytest.raises(pyjwt.ExpiredSignatureError):
            cloud_auth_jwt.validate_cloud_jwt(token)


def test_validate_cloud_jwt_bad_signature(rsa_keypair):
    """JWT signed with wrong key should be rejected."""
    private_key, _ = rsa_keypair
    token = _make_cloud_jwt(private_key)

    # Use a different public key for verification
    other_private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    other_public_key = other_private_key.public_key()

    mock_jwk = MagicMock()
    mock_jwk.key = other_public_key

    mock_jwks_client = MagicMock()
    mock_jwks_client.get_signing_key_from_jwt.return_value = mock_jwk

    with patch.object(cloud_auth_jwt, '_ensure_jwks_client', return_value=mock_jwks_client):
        with pytest.raises(pyjwt.InvalidSignatureError):
            cloud_auth_jwt.validate_cloud_jwt(token)


def test_validate_cloud_jwt_missing_issuer():
    """JWT without issuer claim should be rejected."""
    # Create a token with no issuer
    token = pyjwt.encode({"sub": "test", "exp": int(time.time()) + 3600}, "secret", algorithm="HS256")
    with pytest.raises(pyjwt.InvalidTokenError):
        cloud_auth_jwt.validate_cloud_jwt(token)


def test_validate_cloud_jwt_mismatched_issuer_skips_jwks_fetch(rsa_keypair):
    """Issuer pinned via env var — mismatched tokens MUST be rejected before any network call."""
    private_key, _ = rsa_keypair
    token = _make_cloud_jwt(private_key, issuer="https://attacker.example.com/realms/evil")

    with patch.object(cloud_auth_jwt, "_ensure_jwks_client") as mock_jwks:
        with pytest.raises(pyjwt.InvalidTokenError, match="issuer does not match"):
            cloud_auth_jwt.validate_cloud_jwt(token)
        mock_jwks.assert_not_called()


def test_validate_cloud_jwt_requires_env_var(monkeypatch, rsa_keypair):
    """Unset CLOUD_KEYCLOAK_URL must fail closed, even for a well-formed token."""
    monkeypatch.delenv(cloud_auth_jwt.CLOUD_KEYCLOAK_URL_ENV, raising=False)
    private_key, _ = rsa_keypair
    token = _make_cloud_jwt(private_key)

    with patch.object(cloud_auth_jwt, "_ensure_jwks_client") as mock_jwks:
        with pytest.raises(pyjwt.InvalidTokenError, match="not configured"):
            cloud_auth_jwt.validate_cloud_jwt(token)
        mock_jwks.assert_not_called()


def test_jwks_url_from_issuer():
    """JWKS URL should be derived from Keycloak issuer URL."""
    issuer = "https://keycloak.example.com/realms/errand"
    url = cloud_auth_jwt._get_jwks_url_from_issuer(issuer)
    assert url == "https://keycloak.example.com/realms/errand/protocol/openid-connect/certs"


def test_jwks_client_caching(rsa_keypair):
    """JWKS client should be cached within TTL."""
    # Reset cache
    cloud_auth_jwt._jwks_client = None
    cloud_auth_jwt._jwks_issuer = None
    cloud_auth_jwt._jwks_fetched_at = 0

    issuer = "https://keycloak.example.com/realms/errand"

    with patch('cloud_auth_jwt.PyJWKClient') as mock_class:
        client1 = cloud_auth_jwt._ensure_jwks_client(issuer)
        client2 = cloud_auth_jwt._ensure_jwks_client(issuer)
        # Should only create one client (cached)
        assert mock_class.call_count == 1
        assert client1 is client2


def test_jwks_client_expires(rsa_keypair):
    """JWKS client should be recreated after TTL expires."""
    cloud_auth_jwt._jwks_client = None
    cloud_auth_jwt._jwks_issuer = None
    cloud_auth_jwt._jwks_fetched_at = 0

    issuer = "https://keycloak.example.com/realms/errand"

    with patch('cloud_auth_jwt.PyJWKClient') as mock_class:
        cloud_auth_jwt._ensure_jwks_client(issuer)
        # Simulate TTL expiry
        cloud_auth_jwt._jwks_fetched_at = time.time() - cloud_auth_jwt.JWKS_CACHE_TTL - 1
        cloud_auth_jwt._ensure_jwks_client(issuer)
        # Should have created two clients
        assert mock_class.call_count == 2


def test_proxy_request_marker():
    """PROXY_REQUEST_MARKER constant should be defined."""
    assert cloud_auth_jwt.PROXY_REQUEST_MARKER == "_cloud_proxy_request"


def test_proxy_secret_constants():
    """Proxy secret and header constants should be defined."""
    assert isinstance(cloud_auth_jwt.PROXY_SECRET, str)
    assert len(cloud_auth_jwt.PROXY_SECRET) > 0
    assert cloud_auth_jwt.PROXY_SECRET_HEADER == "X-Proxy-Secret"
