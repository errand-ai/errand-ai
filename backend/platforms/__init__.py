from platforms.base import Platform, PlatformInfo


class PlatformRegistry:
    def __init__(self):
        self._platforms: dict[str, Platform] = {}

    def register(self, platform: Platform) -> None:
        info = platform.info()
        self._platforms[info.id] = platform

    def get(self, platform_id: str) -> Platform | None:
        return self._platforms.get(platform_id)

    def list_all(self) -> list[PlatformInfo]:
        return [p.info() for p in self._platforms.values()]

    async def list_configured(self) -> list[PlatformInfo]:
        from sqlalchemy import select
        from database import async_session
        from models import PlatformCredential

        async with async_session() as session:
            result = await session.execute(
                select(PlatformCredential.platform_id).where(
                    PlatformCredential.status == "connected"
                )
            )
            configured_ids = {row[0] for row in result}

        return [
            p.info()
            for p in self._platforms.values()
            if p.info().id in configured_ids
        ]


_registry: PlatformRegistry | None = None


def get_registry() -> PlatformRegistry:
    global _registry
    if _registry is None:
        _registry = PlatformRegistry()
    return _registry
