import json
import logging
import os
from typing import Optional

from redis.asyncio import Redis

logger = logging.getLogger(__name__)

VALKEY_URL = os.environ.get("VALKEY_URL", "redis://localhost:6379")
CHANNEL = "task_events"

_valkey: Optional[Redis] = None


async def init_valkey() -> None:
    global _valkey
    _valkey = Redis.from_url(VALKEY_URL, decode_responses=True)


async def close_valkey() -> None:
    global _valkey
    if _valkey is not None:
        await _valkey.aclose()
        _valkey = None


def get_valkey() -> Optional[Redis]:
    return _valkey


async def publish_event(event_type: str, task_data: dict) -> None:
    valkey = get_valkey()
    if valkey is None:
        logger.warning("Valkey not connected, skipping event publish: %s", event_type)
        return
    message = json.dumps({"event": event_type, "task": task_data})
    try:
        await valkey.publish(CHANNEL, message)
    except Exception:
        logger.warning("Failed to publish event to Valkey: %s", event_type, exc_info=True)
