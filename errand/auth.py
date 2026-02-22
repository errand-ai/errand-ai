import os
from dataclasses import dataclass, field

import httpx
import jwt
from jwt import PyJWKClient


@dataclass
class OIDCConfig:
    discovery_url: str
    client_id: str
    client_secret: str
    roles_claim: str
    authorization_endpoint: str = ""
    token_endpoint: str = ""
    end_session_endpoint: str = ""
    jwks_uri: str = ""
    issuer: str = ""
    _jwks_client: PyJWKClient | None = field(default=None, repr=False)

    @classmethod
    def from_env(cls, db_settings: dict | None = None) -> "OIDCConfig | None":
        """Returns OIDCConfig from env vars or DB settings, None otherwise."""
        # Try env vars first
        discovery_url = os.environ.get("OIDC_DISCOVERY_URL")
        client_id = os.environ.get("OIDC_CLIENT_ID")
        client_secret = os.environ.get("OIDC_CLIENT_SECRET")
        roles_claim = os.environ.get("OIDC_ROLES_CLAIM", "resource_access.errand.roles")

        if discovery_url and client_id and client_secret:
            return cls(
                discovery_url=discovery_url,
                client_id=client_id,
                client_secret=client_secret,
                roles_claim=roles_claim,
            )

        # Fall back to DB settings
        if db_settings:
            discovery_url = db_settings.get("oidc_discovery_url")
            client_id = db_settings.get("oidc_client_id")
            client_secret = db_settings.get("oidc_client_secret")
            roles_claim = db_settings.get("oidc_roles_claim", "resource_access.errand.roles")
            if discovery_url and client_id and client_secret:
                # Unwrap JSONB string values
                return cls(
                    discovery_url=str(discovery_url),
                    client_id=str(client_id),
                    client_secret=str(client_secret),
                    roles_claim=str(roles_claim),
                )

        return None

    async def discover(self) -> None:
        async with httpx.AsyncClient() as client:
            resp = await client.get(self.discovery_url, timeout=10)
            resp.raise_for_status()
            data = resp.json()

        self.authorization_endpoint = data["authorization_endpoint"]
        self.token_endpoint = data["token_endpoint"]
        self.end_session_endpoint = data["end_session_endpoint"]
        self.jwks_uri = data["jwks_uri"]
        self.issuer = data["issuer"]
        self._jwks_client = PyJWKClient(self.jwks_uri)

    def get_signing_key(self, token: str) -> jwt.PyJWK:
        if self._jwks_client is None:
            raise RuntimeError("OIDC discovery has not been performed")
        return self._jwks_client.get_signing_key_from_jwt(token)

    def decode_token(self, token: str) -> dict:
        try:
            signing_key = self.get_signing_key(token)
        except jwt.exceptions.PyJWKClientError:
            # Key not found — refresh JWKS and retry once
            self._jwks_client = PyJWKClient(self.jwks_uri)
            signing_key = self.get_signing_key(token)

        return jwt.decode(
            token,
            signing_key.key,
            algorithms=["RS256"],
            issuer=self.issuer,
            options={"verify_aud": False, "require": ["exp", "iss"]},
        )

    def extract_roles(self, claims: dict) -> list[str]:
        obj = claims
        for part in self.roles_claim.split("."):
            if isinstance(obj, dict):
                obj = obj.get(part)
            else:
                return []
            if obj is None:
                return []
        if isinstance(obj, list):
            return obj
        return []


# Module-level singleton, initialized during app lifespan
oidc: OIDCConfig | None = None
