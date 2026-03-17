import asyncio
import email
import logging
import uuid
from datetime import datetime, timezone
from email import policy
from email.message import EmailMessage

import aioimaplib
import html2text
from sqlalchemy import func, select

from database import async_session
from events import publish_event
from llm import generate_title
from models import Task, TaskGenerator
from platforms.credentials import load_credentials

logger = logging.getLogger(__name__)

CREDENTIAL_CHECK_INTERVAL = 30  # seconds between checks when no credentials configured
MAX_BODY_LENGTH = 50_000
IDLE_TIMEOUT = 600  # 10 minutes
SAFETY_POLL_CYCLES = 6  # full UNSEEN check every N IDLE cycles
MIN_POLL_INTERVAL = 60
BACKOFF_INITIAL = 5
BACKOFF_MAX = 300
BACKOFF_FACTOR = 2


async def connect_imap(credentials: dict) -> tuple[aioimaplib.IMAP4_SSL | aioimaplib.IMAP4, bool]:
    """Connect to IMAP, login, and check IDLE capability.

    Returns (imap_client, idle_supported).
    """
    host = credentials["imap_host"]
    port = int(credentials["imap_port"])
    username = credentials["username"]
    password = credentials["password"]
    security = credentials.get("security", "ssl")

    # Determine IMAP security from port (993=SSL, 143=STARTTLS, else follow toggle)
    use_ssl = port == 993 or (port != 143 and security == "ssl")

    if use_ssl:
        imap = aioimaplib.IMAP4_SSL(host=host, port=port)
    else:
        imap = aioimaplib.IMAP4(host=host, port=port)

    await imap.wait_hello_from_server()

    if not use_ssl:
        await imap.starttls()

    await imap.login(username, password)
    await imap.select("INBOX")

    # Check IDLE capability
    idle_supported = imap.has_capability("IDLE")
    logger.info("IMAP connected to %s:%d (IDLE %s)", host, port, "supported" if idle_supported else "not supported")

    return imap, idle_supported


def extract_body(raw_bytes: bytes) -> str:
    """Parse MIME message and return markdown body, truncated to MAX_BODY_LENGTH."""
    msg = email.message_from_bytes(raw_bytes, policy=policy.default)

    html_part = None
    text_part = None

    if msg.is_multipart():
        for part in msg.walk():
            content_type = part.get_content_type()
            if content_type == "text/html" and html_part is None:
                html_part = part.get_content()
            elif content_type == "text/plain" and text_part is None:
                text_part = part.get_content()
    else:
        content_type = msg.get_content_type()
        if content_type == "text/html":
            html_part = msg.get_content()
        elif content_type == "text/plain":
            text_part = msg.get_content()

    if html_part:
        h = html2text.HTML2Text()
        h.ignore_links = False
        h.ignore_images = True
        h.body_width = 0
        body = h.handle(html_part)
    elif text_part:
        body = text_part
    else:
        body = ""

    return body[:MAX_BODY_LENGTH]


def build_description(sender: str, to: str, date: str, subject: str, uid: str, body: str, task_prompt: str | None = None) -> str:
    """Build task description with email metadata, markdown body, and optional task prompt."""
    desc = (
        f"**From:** {sender}\n"
        f"**To:** {to}\n"
        f"**Date:** {date}\n"
        f"**Subject:** {subject}\n"
        f"**Email UID:** {uid}\n"
        "\n---\n\n"
        f"{body}"
    )
    if task_prompt:
        desc += "\n\n---\n\n**Additional Instructions:**\n\n" + task_prompt
    return desc


async def create_task_from_email(
    subject: str, description: str, profile_id: str | None,
) -> bool:
    """Create a task from an email. Returns True on success."""
    async with async_session() as session:
        # Get next position for pending column
        result = await session.execute(
            select(func.max(Task.position)).where(Task.status == "pending")
        )
        max_pos = result.scalar()
        position = (max_pos or 0) + 1

        resolved_profile_id = None
        if profile_id:
            try:
                resolved_profile_id = uuid.UUID(profile_id)
            except (ValueError, TypeError):
                logger.warning("Invalid profile_id '%s', creating task without profile", profile_id)

        # Generate a short title via LLM (same as API-created tasks)
        title = subject or "(no subject)"
        try:
            llm_result = await generate_title(description, session, now=datetime.now(timezone.utc))
            if llm_result.success and llm_result.title:
                title = llm_result.title
        except Exception:
            logger.warning("LLM title generation failed for email, using subject as title")

        task = Task(
            title=title,
            description=description,
            status="pending",
            position=position,
            category="immediate",
            execute_at=datetime.now(timezone.utc),
            profile_id=resolved_profile_id,
            created_by="email_poller",
        )
        session.add(task)
        await session.commit()
        await session.refresh(task)

        task_data = {
            "id": str(task.id),
            "title": task.title,
            "description": task.description,
            "status": task.status,
            "position": task.position,
            "category": task.category,
            "execute_at": None,
            "repeat_interval": None,
            "repeat_until": None,
            "output": None,
            "runner_logs": None,
            "questions": None,
            "retry_count": 0,
            "profile_id": str(task.profile_id) if task.profile_id else None,
            "profile_name": None,
            "tags": [],
            "created_at": task.created_at.isoformat() if task.created_at else None,
            "updated_at": task.updated_at.isoformat() if task.updated_at else None,
            "created_by": task.created_by,
            "updated_by": task.updated_by,
        }
        await publish_event("task_created", task_data)
        logger.info("Created task '%s' from email UID (profile=%s)", task.title, profile_id)
        return True


async def _load_email_generator() -> TaskGenerator | None:
    """Load the email task generator record from the database."""
    async with async_session() as session:
        result = await session.execute(
            select(TaskGenerator).where(TaskGenerator.type == "email")
        )
        return result.scalar_one_or_none()


async def process_messages(imap, generator: TaskGenerator) -> int:
    """Fetch and process UNSEEN messages. Returns count of tasks created."""
    response = await imap.search("UNSEEN")
    if response.result != "OK":
        logger.warning("IMAP SEARCH UNSEEN failed: %s", response.lines)
        return 0

    # response.lines[0] is space-separated UIDs (or empty)
    uid_line = response.lines[0]
    if not uid_line or not uid_line.strip():
        logger.debug("SEARCH UNSEEN returned no UIDs")
        return 0

    uids = uid_line.strip().split()
    logger.info("Found %d unseen message(s): %s", len(uids), " ".join(
        u.decode() if isinstance(u, bytes) else str(u) for u in uids[:10]
    ))
    created = 0

    profile_id = str(generator.profile_id) if generator.profile_id else None
    config = generator.config or {}
    task_prompt = config.get("task_prompt")

    for uid in uids:
        uid_str = uid.decode() if isinstance(uid, bytes) else str(uid)
        try:
            fetch_response = await imap.fetch(uid_str, "(RFC822)")
            if fetch_response.result != "OK":
                logger.warning("IMAP FETCH failed for UID %s: %s", uid_str, fetch_response.lines)
                continue

            # Parse the fetch response to extract raw email bytes.
            # aioimaplib returns bytearray for literal data (email content)
            # and bytes for protocol lines — prefer bytearray entries.
            raw_email = None
            for line in fetch_response.lines:
                if isinstance(line, bytearray) and len(line) > 0:
                    raw_email = bytes(line)
                    break
                elif isinstance(line, bytes) and len(line) > 0:
                    if raw_email is None or len(line) > len(raw_email):
                        raw_email = line

            if raw_email is None:
                logger.warning("No email body found for UID %s", uid_str)
                continue

            msg = email.message_from_bytes(raw_email, policy=policy.default)
            sender = str(msg.get("From", ""))
            to = str(msg.get("To", ""))
            date = str(msg.get("Date", ""))
            subject = str(msg.get("Subject", ""))

            body = extract_body(raw_email)
            description = build_description(sender, to, date, subject, uid_str, body, task_prompt)

            success = await create_task_from_email(subject, description, profile_id)
            if success:
                # Mark as read
                await imap.store(uid_str, "+FLAGS", "\\Seen")
                created += 1

        except Exception:
            logger.exception("Error processing email UID %s", uid_str)
            continue

    return created


async def run_email_poller():
    """Background task that polls for new emails and creates tasks."""
    backoff = BACKOFF_INITIAL

    while True:
        try:
            # Check for email credentials (IMAP connection details)
            async with async_session() as session:
                credentials = await load_credentials("email", session)

            if not credentials:
                logger.debug("No email credentials configured, waiting...")
                await asyncio.sleep(CREDENTIAL_CHECK_INTERVAL)
                continue

            # Check for enabled email task generator
            generator = await _load_email_generator()
            if not generator or not generator.enabled:
                logger.debug("Email task generator not enabled, waiting...")
                await asyncio.sleep(CREDENTIAL_CHECK_INTERVAL)
                continue

            imap, idle_supported = await connect_imap(credentials)
            backoff = BACKOFF_INITIAL  # reset on successful connection

            try:
                if idle_supported:
                    await _run_idle_loop(imap, generator)
                else:
                    await _run_poll_loop(imap, generator)
            finally:
                try:
                    await imap.logout()
                except Exception:
                    pass

        except asyncio.CancelledError:
            logger.info("Email poller shutting down")
            raise
        except Exception:
            logger.exception("Email poller error, retrying in %ds", backoff)
            await asyncio.sleep(backoff)
            backoff = min(backoff * BACKOFF_FACTOR, BACKOFF_MAX)


async def _run_idle_loop(imap, generator: TaskGenerator):
    """IMAP IDLE loop with safety polls."""
    cycle = 0

    while True:
        # Re-read generator config and verify credentials still exist
        fresh_generator = await _load_email_generator()
        if not fresh_generator or not fresh_generator.enabled:
            logger.info("Email task generator disabled, exiting IDLE loop")
            return

        async with async_session() as session:
            credentials = await load_credentials("email", session)
        if not credentials:
            logger.info("Email credentials removed, exiting IDLE loop")
            return

        # Safety poll every N cycles
        if cycle % SAFETY_POLL_CYCLES == 0:
            logger.info("Safety poll (cycle %d)", cycle)
            count = await process_messages(imap, fresh_generator)
            if count:
                logger.info("Safety poll: created %d tasks", count)
            else:
                logger.info("Safety poll: no unseen messages")

        # Enter IDLE
        logger.debug("Entering IDLE (cycle %d, timeout=%ds)", cycle, IDLE_TIMEOUT)
        idle_task = await imap.idle_start(timeout=IDLE_TIMEOUT)
        await imap.wait_server_push(timeout=IDLE_TIMEOUT + 30)
        imap.idle_done()
        await asyncio.wait_for(idle_task, timeout=10)

        # Process any new messages after IDLE notification/timeout
        fresh_generator = await _load_email_generator()
        if fresh_generator and fresh_generator.enabled:
            count = await process_messages(imap, fresh_generator)
            if count:
                logger.info("IDLE notification: created %d tasks", count)

        cycle += 1


async def _run_poll_loop(imap, generator: TaskGenerator):
    """Polling fallback when IDLE is not supported."""
    while True:
        # Re-read generator config and verify credentials still exist
        fresh_generator = await _load_email_generator()
        if not fresh_generator or not fresh_generator.enabled:
            logger.info("Email task generator disabled, exiting poll loop")
            return

        async with async_session() as session:
            credentials = await load_credentials("email", session)
        if not credentials:
            logger.info("Email credentials removed, exiting poll loop")
            return

        count = await process_messages(imap, fresh_generator)
        if count:
            logger.info("Poll: created %d tasks", count)

        poll_interval = _get_poll_interval(fresh_generator)
        await asyncio.sleep(poll_interval)


def _get_poll_interval(generator: TaskGenerator) -> int:
    """Get poll interval from task generator config, enforcing minimum of 60 seconds."""
    config = generator.config or {}
    try:
        interval = int(config.get("poll_interval", MIN_POLL_INTERVAL))
    except (ValueError, TypeError):
        interval = MIN_POLL_INTERVAL
    return max(interval, MIN_POLL_INTERVAL)
