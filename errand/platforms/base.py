from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import StrEnum


class PlatformCapability(StrEnum):
    POST = "post"
    MEDIA = "media"
    COMMANDS = "commands"
    WEBHOOKS = "webhooks"
    ANALYTICS = "analytics"
    MONITORING = "monitoring"
    EMAIL = "email"


@dataclass
class PlatformInfo:
    id: str
    label: str
    capabilities: set[PlatformCapability]
    credential_schema: list[dict]


@dataclass
class PostResult:
    success: bool
    url: str | None = None
    error: str | None = None


class Platform(ABC):
    @abstractmethod
    def info(self) -> PlatformInfo:
        pass

    @abstractmethod
    async def verify_credentials(self, credentials: dict) -> bool:
        pass

    async def post(self, message: str, **kwargs) -> PostResult:
        raise NotImplementedError

    async def delete_post(self, post_id: str) -> bool:
        raise NotImplementedError

    async def get_post(self, post_id: str) -> dict | None:
        raise NotImplementedError
