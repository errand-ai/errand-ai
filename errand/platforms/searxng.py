import logging

import httpx

from platforms.base import Platform, PlatformCapability, PlatformInfo

logger = logging.getLogger(__name__)

DEFAULT_URL = "https://search.errand.cloud"


class SearXNGPlatform(Platform):
    def info(self) -> PlatformInfo:
        return PlatformInfo(
            id="searxng",
            label="SearXNG Search",
            capabilities={PlatformCapability.SEARCH},
            credential_schema=[
                {"key": "url", "label": "Instance URL", "type": "text", "required": True, "default": DEFAULT_URL},
                {"key": "username", "label": "Username", "type": "text", "required": False},
                {"key": "password", "label": "Password", "type": "password", "required": False},
            ],
        )

    async def verify_credentials(self, credentials: dict) -> bool:
        url = credentials.get("url", "").rstrip("/")
        username = credentials.get("username")
        password = credentials.get("password")

        auth = None
        if username and password:
            auth = httpx.BasicAuth(username, password)

        try:
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.get(
                    f"{url}/search",
                    params={"q": "test", "format": "json"},
                    auth=auth,
                )
                if resp.status_code != 200:
                    return False
                data = resp.json()
                return "results" in data
        except Exception:
            logger.exception("SearXNG credential verification failed")
            return False

    async def search(self, query: str, **kwargs) -> dict:
        credentials = kwargs.get("credentials", {})
        url = credentials.get("url", DEFAULT_URL).rstrip("/")
        username = credentials.get("username")
        password = credentials.get("password")

        auth = None
        if username and password:
            auth = httpx.BasicAuth(username, password)

        params = {"q": query, "format": "json"}
        for key in ("categories", "time_range", "language", "safesearch", "pageno"):
            if key in kwargs and kwargs[key] is not None:
                params[key] = kwargs[key]

        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(f"{url}/search", params=params, auth=auth)
            resp.raise_for_status()
            data = resp.json()

        return {
            "query": query,
            "results": [
                {
                    "title": r.get("title", ""),
                    "url": r.get("url", ""),
                    "content": r.get("content", ""),
                    "engines": r.get("engines", []),
                    "score": r.get("score", 0.0),
                }
                for r in data.get("results", [])
            ],
            "suggestions": data.get("suggestions", []),
            "number_of_results": data.get("number_of_results", 0),
        }
