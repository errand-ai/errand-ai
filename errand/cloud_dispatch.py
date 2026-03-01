"""Cloud webhook dispatcher.

Routes incoming webhook payloads from errand-cloud relay to the appropriate
Slack processing functions based on integration and endpoint_type.
"""
import logging

from database import async_session

logger = logging.getLogger(__name__)


async def dispatch_cloud_webhook(message: dict) -> None:
    """Route a cloud-relayed webhook to the appropriate handler.

    The message follows the errand-client-protocol webhook format:
    {
        "type": "webhook",
        "id": "<uuid>",
        "integration": "<type>",
        "endpoint_type": "<type>",
        "body": "<raw_body_string>",
        "headers": {...},
        ...
    }
    """
    integration = message.get("integration", "")
    endpoint_type = message.get("endpoint_type", "")
    body = message.get("body", "")

    # Convert body string to bytes for handler compatibility
    body_bytes = body.encode("utf-8") if isinstance(body, str) else body

    if integration == "slack":
        await _dispatch_slack(endpoint_type, body_bytes)
    else:
        logger.warning("Unknown cloud webhook integration: %s", integration)


async def _dispatch_slack(endpoint_type: str, body: bytes) -> None:
    """Dispatch a Slack webhook payload to the appropriate handler."""
    from platforms.slack.routes import (
        process_slack_command,
        process_slack_event,
        process_slack_interaction,
    )

    if endpoint_type == "events":
        await process_slack_event(body)

    elif endpoint_type == "commands":
        async with async_session() as session:
            await process_slack_command(body, session, response_url_callback="cloud")

    elif endpoint_type == "interactivity":
        async with async_session() as session:
            await process_slack_interaction(body, session)

    else:
        logger.warning("Unknown Slack endpoint type from cloud: %s", endpoint_type)
