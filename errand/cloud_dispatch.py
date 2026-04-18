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
    elif integration == "jira" and endpoint_type == "webhook":
        trigger_id = message.get("trigger_id")
        headers = message.get("headers", {})
        await _dispatch_jira_webhook(body_bytes, headers, trigger_id)
    elif integration == "github" and endpoint_type == "webhook":
        trigger_id = message.get("trigger_id")
        headers = message.get("headers", {})
        await _dispatch_github_webhook(body_bytes, headers, trigger_id)
    else:
        logger.warning("Unknown cloud webhook integration: %s", integration)


async def _dispatch_jira_webhook(body: bytes, headers: dict, trigger_id: str | None) -> None:
    """Dispatch a Jira webhook payload received via cloud relay."""
    if not trigger_id:
        logger.warning("Jira webhook relay missing trigger_id, discarding")
        return

    import uuid
    from sqlalchemy import select
    from models import WebhookTrigger
    from webhook_receiver import _verify_hmac
    from platforms.credentials import decrypt

    try:
        parsed_id = uuid.UUID(trigger_id)
    except (ValueError, AttributeError):
        logger.warning("Invalid trigger_id in relay message: %s", trigger_id)
        return

    async with async_session() as session:
        result = await session.execute(
            select(WebhookTrigger).where(WebhookTrigger.id == parsed_id)
        )
        trigger = result.scalar_one_or_none()

    if not trigger:
        logger.warning("Trigger %s not found, discarding relay message", trigger_id)
        return

    if not trigger.enabled:
        logger.warning("Trigger %s is disabled, discarding relay message", trigger_id)
        return

    # Re-verify HMAC for defense in depth
    signature = headers.get("x-hub-signature", headers.get("X-Hub-Signature", ""))
    if trigger.webhook_secret:
        if not signature:
            logger.warning("Trigger %s has a secret but relay message has no signature, discarding", trigger_id)
            return
        try:
            cred_data = decrypt(trigger.webhook_secret)
            secret = cred_data.get("secret", "")
            if not _verify_hmac(secret, body, signature):
                logger.warning("HMAC re-verification failed for trigger %s", trigger_id)
                return
        except Exception:
            logger.warning("Failed to decrypt secret for trigger %s during re-verification", trigger_id)
            return

    try:
        from platforms.jira.handler import handle_jira_webhook
        await handle_jira_webhook(trigger, body, headers)
    except Exception:
        logger.exception("Error processing Jira webhook for trigger %s", trigger_id)


async def _dispatch_github_webhook(body: bytes, headers: dict, trigger_id: str | None) -> None:
    """Dispatch a GitHub webhook payload received via cloud relay."""
    if not trigger_id:
        logger.warning("GitHub webhook relay missing trigger_id, discarding")
        return

    import uuid
    from sqlalchemy import select
    from models import WebhookTrigger
    from webhook_receiver import _verify_hmac
    from platforms.credentials import decrypt

    try:
        parsed_id = uuid.UUID(trigger_id)
    except (ValueError, AttributeError):
        logger.warning("Invalid trigger_id in relay message: %s", trigger_id)
        return

    async with async_session() as session:
        result = await session.execute(
            select(WebhookTrigger).where(WebhookTrigger.id == parsed_id)
        )
        trigger = result.scalar_one_or_none()

    if not trigger:
        logger.warning("Trigger %s not found, discarding relay message", trigger_id)
        return

    if not trigger.enabled:
        logger.warning("Trigger %s is disabled, discarding relay message", trigger_id)
        return

    # Re-verify HMAC for defense in depth
    signature = headers.get("x-hub-signature-256", headers.get("X-Hub-Signature-256", ""))
    if trigger.webhook_secret:
        if not signature:
            logger.warning("Trigger %s has a secret but relay message has no signature, discarding", trigger_id)
            return
        try:
            cred_data = decrypt(trigger.webhook_secret)
            secret = cred_data.get("secret", "")
            if not _verify_hmac(secret, body, signature):
                logger.warning("HMAC re-verification failed for trigger %s", trigger_id)
                return
        except Exception:
            logger.warning("Failed to decrypt secret for trigger %s during re-verification", trigger_id)
            return

    try:
        from platforms.github.handler import handle_github_webhook
        await handle_github_webhook(trigger, body, headers)
    except Exception:
        logger.exception("Error processing GitHub webhook for trigger %s", trigger_id)


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
            await process_slack_command(body, session, use_response_url="cloud")

    elif endpoint_type == "interactivity":
        async with async_session() as session:
            await process_slack_interaction(body, session)

    else:
        logger.warning("Unknown Slack endpoint type from cloud: %s", endpoint_type)
