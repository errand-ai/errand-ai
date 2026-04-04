import logging
import time

import httpx
import jwt

from platforms.base import Platform, PlatformInfo

logger = logging.getLogger(__name__)

GITHUB_API_BASE = "https://api.github.com"


def mint_installation_token(app_id: str, private_key: str, installation_id: str) -> str:
    """Mint an ephemeral GitHub App installation access token (1-hour TTL)."""
    now = int(time.time())
    payload = {"iss": app_id, "iat": now - 60, "exp": now + 600}
    encoded_jwt = jwt.encode(payload, private_key, algorithm="RS256")

    response = httpx.post(
        f"{GITHUB_API_BASE}/app/installations/{installation_id}/access_tokens",
        headers={
            "Authorization": f"Bearer {encoded_jwt}",
            "Accept": "application/vnd.github+json",
        },
        timeout=10,
    )
    if response.status_code != 201:
        raise RuntimeError(
            f"GitHub App token minting failed: HTTP {response.status_code} - {response.text}"
        )
    return response.json()["token"]


class GitHubPlatform(Platform):
    def info(self) -> PlatformInfo:
        return PlatformInfo(
            id="github",
            label="GitHub",
            capabilities=set(),
            credential_schema=[
                {"key": "auth_mode", "label": "Auth Mode", "type": "select",
                 "options": [{"value": "pat", "label": "Personal Access Token"},
                             {"value": "app", "label": "GitHub App"}],
                 "required": True},
                {"key": "personal_access_token", "label": "Personal Access Token",
                 "type": "password", "required": True, "auth_mode": "pat"},
                {"key": "app_id", "label": "App ID",
                 "type": "text", "required": True, "auth_mode": "app"},
                {"key": "private_key", "label": "Private Key (PEM)",
                 "type": "textarea", "required": True, "auth_mode": "app"},
                {"key": "installation_id", "label": "Installation ID",
                 "type": "text", "required": True, "auth_mode": "app"},
            ],
        )

    async def verify_credentials(self, credentials: dict) -> bool:
        auth_mode = credentials.get("auth_mode", "pat")

        if auth_mode == "pat":
            return await self._verify_pat(credentials)
        elif auth_mode == "app":
            return await self._verify_app(credentials)
        else:
            logger.error("Unknown GitHub auth_mode: %s", auth_mode)
            return False

    async def _verify_pat(self, credentials: dict) -> bool:
        token = credentials.get("personal_access_token", "")
        if not token:
            logger.warning("GitHub PAT verification: no token provided")
            return False
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    f"{GITHUB_API_BASE}/user",
                    headers={
                        "Authorization": f"token {token}",
                        "Accept": "application/vnd.github+json",
                    },
                    timeout=10,
                )
            if response.status_code != 200:
                logger.warning("GitHub PAT verification failed: HTTP %s", response.status_code)
            return response.status_code == 200
        except Exception:
            logger.exception("GitHub PAT verification failed")
            return False

    async def _verify_app(self, credentials: dict) -> bool:
        try:
            mint_installation_token(
                app_id=credentials["app_id"],
                private_key=credentials["private_key"],
                installation_id=credentials["installation_id"],
            )
            return True
        except Exception:
            logger.exception("GitHub App credential verification failed")
            return False
