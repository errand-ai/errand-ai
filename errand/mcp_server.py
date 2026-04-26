import email as email_module
import html2text
import json
import logging
import re
import secrets
import uuid as uuid_mod
from email.message import EmailMessage
from datetime import datetime

import httpx

from mcp.server.auth.provider import AccessToken, TokenVerifier
from mcp.server.auth.settings import AuthSettings
from mcp.server.fastmcp import Context, FastMCP
from mcp.server.transport_security import TransportSecuritySettings
from pydantic import AnyHttpUrl
from sqlalchemy import func, select
from starlette.applications import Starlette

from database import async_session
from events import publish_event
from llm import generate_title, ProfileInfo
from models import Setting, Skill, SkillFile, Task, TaskProfile
from task_manager import normalize_interval

logger = logging.getLogger(__name__)


class ApiKeyVerifier(TokenVerifier):
    """Validates Bearer token against the stored mcp_api_key setting."""

    async def verify_token(self, token: str) -> AccessToken | None:
        async with async_session() as session:
            result = await session.execute(
                select(Setting.value).where(Setting.key == "mcp_api_key")
            )
            stored_key = result.scalar_one_or_none()

        if stored_key is None:
            return None

        if not secrets.compare_digest(token, stored_key):
            return None

        return AccessToken(token=token, client_id="mcp-client", scopes=[])


mcp = FastMCP(
    "Errand",
    token_verifier=ApiKeyVerifier(),
    auth=AuthSettings(
        issuer_url=AnyHttpUrl("https://localhost"),
        resource_server_url=AnyHttpUrl("https://localhost"),
    ),
    transport_security=TransportSecuritySettings(
        enable_dns_rebinding_protection=False,
    ),
    stateless_http=True,
    json_response=True,
    streamable_http_path="/",
)

# Wrap the tool manager's call_tool to log which tool is being invoked
_original_tm_call_tool = mcp._tool_manager.call_tool


async def _logging_call_tool(name, arguments, **kwargs):
    # Log key identifying arguments for debugging
    detail = ""
    if arguments:
        if name in ("upsert_skill", "delete_skill") and "name" in arguments:
            detail = f" name={arguments['name']!r}"
        elif name == "new_task" and "title" in arguments:
            detail = f" title={arguments['title']!r}"
        elif name == "task_status" and "task_id" in arguments:
            detail = f" task_id={arguments['task_id']}"
    logger.info("MCP tool call: %s%s", name, detail)
    result = await _original_tm_call_tool(name, arguments, **kwargs)
    # Log first 200 chars of result for debugging
    if result:
        result_str = str(result[0].text if hasattr(result, '__getitem__') and hasattr(result[0], 'text') else result)[:200]
        logger.info("MCP tool result: %s → %s", name, result_str)
    return result


mcp._tool_manager.call_tool = _logging_call_tool


def _encrypt_env(env_dict: dict) -> str:
    """Encrypt a dict of env vars using the platform Fernet cipher."""
    from platforms.credentials import encrypt
    return encrypt(env_dict)


def _validate_and_encrypt_env(env: dict | None) -> tuple[str | None, str | None]:
    """Validate and encrypt per-task env vars. Returns (encrypted_env, error_message)."""
    if not env:
        return None, None
    if not isinstance(env, dict) or not all(isinstance(k, str) and isinstance(v, str) for k, v in env.items()):
        return None, "Error: Invalid env value. Expected an object mapping strings to strings."
    try:
        return _encrypt_env(env), None
    except RuntimeError:
        return None, "Error: Cannot store encrypted env vars — encryption key not configured."


def _get_client_id(ctx: Context | None) -> str:
    """Extract X-Client-Id header from MCP request context, defaulting to 'mcp'."""
    if ctx and ctx.request_context and ctx.request_context.request:
        client_id = ctx.request_context.request.headers.get("x-client-id")
        if client_id and client_id.strip():
            return client_id.strip()
    return "mcp"


@mcp.tool()
async def new_task(
    description: str,
    profile: str | None = None,
    title: str | None = None,
    env: dict | None = None,
    ctx: Context | None = None,
) -> str:
    """Create a new task from a description. Returns the task UUID.

    Args:
        description: The task description.
        profile: Optional name of a task profile to assign.
        title: Optional task title. When set, the title and description are used
            verbatim and the LLM summariser is skipped.
        env: Optional object of environment variable key/value pairs to inject
            into the task-runner container. Values are stored encrypted.
    """
    async with async_session() as session:
        category = "immediate"
        resolved_profile_id = None

        # If explicit profile provided, resolve it first
        if profile:
            prof_result = await session.execute(select(TaskProfile).where(TaskProfile.name == profile))
            found = prof_result.scalar_one_or_none()
            if not found:
                return f"Error: Task profile '{profile}' not found."
            resolved_profile_id = found.id

        if title:
            # Explicit title — skip LLM summariser, store description verbatim
            cleaned_description = description or None
        else:
            words = description.strip().split()
            if len(words) > 5:
                # Load profiles for classification (only if no explicit profile)
                if not profile:
                    prof_result = await session.execute(select(TaskProfile).order_by(TaskProfile.name))
                    db_profiles = prof_result.scalars().all()
                    profile_infos = [ProfileInfo(name=p.name, match_rules=p.match_rules) for p in db_profiles] if db_profiles else None
                else:
                    profile_infos = None

                llm_result = await generate_title(description, session, profiles=profile_infos)
                title = llm_result.title
                category = llm_result.category or "immediate"
                if not llm_result.success:
                    cleaned_description = description.strip()
                else:
                    cleaned_description = llm_result.description

                # Resolve profile name to ID from LLM suggestion (only if no explicit profile)
                if not profile and llm_result.profile and db_profiles:
                    profile_map = {p.name: p.id for p in db_profiles}
                    resolved_profile_id = profile_map.get(llm_result.profile)
            else:
                title = description.strip()
                cleaned_description = None

        # Encrypt per-task env vars if provided
        encrypted_env, env_error = _validate_and_encrypt_env(env)
        if env_error:
            return env_error

        # Auto-route based on category (same logic as main task creation)
        if category in ("scheduled", "repeating"):
            status = "scheduled"
        else:
            status = "pending"

        # Get next position for target status column
        result = await session.execute(
            select(func.max(Task.position)).where(Task.status == status)
        )
        max_pos = result.scalar()
        position = (max_pos or 0) + 1

        task = Task(
            title=title,
            description=cleaned_description,
            category=category,
            status=status,
            position=position,
            profile_id=resolved_profile_id,
            encrypted_env=encrypted_env,
            created_by=_get_client_id(ctx),
        )
        session.add(task)
        await session.commit()
        await session.refresh(task, ["tags"])

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
            "retry_count": 0,
            "profile_id": str(task.profile_id) if task.profile_id else None,
            "profile_name": None,
            "tags": [],
            "created_at": task.created_at.isoformat(),
            "updated_at": task.updated_at.isoformat(),
        }
        await publish_event("task_created", task_data)

        return str(task.id)


@mcp.tool()
async def list_task_profiles() -> str:
    """List available task profiles. Returns JSON array of {name, description, model} per profile."""
    async with async_session() as session:
        result = await session.execute(select(TaskProfile).order_by(TaskProfile.name))
        profiles = result.scalars().all()
        return json.dumps([
            {"name": p.name, "description": p.description, "model": p.model}
            for p in profiles
        ])


_SKILL_NAME_RE = re.compile(r"^[a-z0-9]([a-z0-9-]*[a-z0-9])?$")
_ALLOWED_SKILL_FILE_SUBDIRS = {"scripts", "references", "assets"}


def _validate_skill_name(name: str) -> str | None:
    """Validate skill name (relaxed for MCP — allows consecutive hyphens). Returns error message or None."""
    if not name:
        return "Name is required"
    if len(name) > 64:
        return "Name must be at most 64 characters"
    if name != name.lower():
        return "Name must be lowercase"
    if not _SKILL_NAME_RE.match(name):
        return "Name must contain only lowercase letters, digits, and hyphens, and must not start or end with a hyphen"
    return None


@mcp.tool()
async def list_skills() -> str:
    """List available skills. Returns JSON array of {name, description} per skill."""
    async with async_session() as session:
        result = await session.execute(select(Skill).order_by(Skill.name))
        skills = result.scalars().all()
        return json.dumps([
            {"name": s.name, "description": s.description}
            for s in skills
        ])


@mcp.tool()
async def upsert_skill(name: str, description: str, instructions: str, files: list | None = None) -> str:
    """Create or update a skill by name. Returns success message with skill ID.

    Args:
        name: Skill name (lowercase, max 64 chars, letters/digits/hyphens only).
        description: Short description of the skill (max 1024 chars).
        instructions: Full markdown instructions for the skill.
        files: Optional array of {path, content} objects. Paths must be in
            scripts/, references/, or assets/ subdirectories.
    """
    error = _validate_skill_name(name)
    if error:
        return f"Error: {error}"
    if len(description) > 1024:
        return "Error: Description must be at most 1024 characters"

    # Validate files if provided
    file_list = files or []
    if file_list:
        for f in file_list:
            if not isinstance(f, dict) or "path" not in f or "content" not in f:
                return "Error: Each file must be an object with 'path' and 'content' keys"
            if not isinstance(f["path"], str) or not f["path"]:
                return "Error: Each file 'path' must be a non-empty string"
            if not isinstance(f["content"], str):
                return "Error: Each file 'content' must be a string"
            path = f["path"]
            parts = path.split("/")
            if len(parts) != 2 or not parts[0] or not parts[1]:
                return f"Error: Invalid file path '{path}' — must be subdir/filename"
            if parts[0] not in _ALLOWED_SKILL_FILE_SUBDIRS:
                return f"Error: Invalid file path '{path}' — must be in scripts/, references/, or assets/"
        paths = [f["path"] for f in file_list]
        if len(paths) != len(set(paths)):
            return "Error: Duplicate file paths are not allowed"

    async with async_session() as session:
        result = await session.execute(select(Skill).where(Skill.name == name))
        existing = result.scalar_one_or_none()

        if existing:
            existing.description = description
            existing.instructions = instructions
            # Replace all files
            from sqlalchemy import delete
            await session.execute(delete(SkillFile).where(SkillFile.skill_id == existing.id))
            for f in file_list:
                session.add(SkillFile(skill_id=existing.id, path=f["path"], content=f["content"]))
            await session.commit()
            return f"Skill '{name}' updated (id: {existing.id})"
        else:
            skill = Skill(name=name, description=description, instructions=instructions)
            session.add(skill)
            await session.flush()
            for f in file_list:
                session.add(SkillFile(skill_id=skill.id, path=f["path"], content=f["content"]))
            await session.commit()
            return f"Skill '{name}' created (id: {skill.id})"


@mcp.tool()
async def delete_skill(name: str) -> str:
    """Delete a skill by name.

    Args:
        name: The name of the skill to delete.
    """
    async with async_session() as session:
        result = await session.execute(select(Skill).where(Skill.name == name))
        skill = result.scalar_one_or_none()
        if not skill:
            return f"Error: Skill '{name}' not found."
        await session.delete(skill)
        await session.commit()
        return f"Skill '{name}' deleted."


@mcp.tool()
async def task_status(task_id: str, format: str = "text") -> str:
    """Get the current status and details of a task by UUID.

    Args:
        task_id: The UUID of the task.
        format: Output format — "text" (default) for plaintext, "json" for structured JSON.
    """
    if format not in ("text", "json"):
        return f"Error: Unsupported format '{format}'. Supported formats are 'text' and 'json'."
    async with async_session() as session:
        result = await session.execute(select(Task).where(Task.id == uuid_mod.UUID(task_id)))
        task = result.scalar_one_or_none()

        if task is None:
            return f"Error: Task {task_id} not found."

        if format == "json":
            return json.dumps({
                "id": str(task.id),
                "title": task.title,
                "status": task.status,
                "category": task.category,
                "created_at": task.created_at.isoformat(),
                "updated_at": task.updated_at.isoformat(),
                "has_output": bool(task.output),
            })

        return (
            f"Title: {task.title}\n"
            f"Status: {task.status}\n"
            f"Category: {task.category}\n"
            f"Created: {task.created_at.isoformat()}\n"
            f"Updated: {task.updated_at.isoformat()}"
        )


@mcp.tool()
async def task_output(task_id: str) -> str:
    """Get the output of a completed task by UUID."""
    async with async_session() as session:
        result = await session.execute(select(Task).where(Task.id == uuid_mod.UUID(task_id)))
        task = result.scalar_one_or_none()

        if task is None:
            return f"Error: Task {task_id} not found."

        if task.status in ("completed", "review"):
            return task.output or "(no output)"

        return f"Task is still in progress (status: {task.status})"



@mcp.tool()
async def task_logs(task_id: str) -> str:
    """Get the runner execution logs of a task by UUID."""
    async with async_session() as session:
        result = await session.execute(select(Task).where(Task.id == uuid_mod.UUID(task_id)))
        task = result.scalar_one_or_none()

        if task is None:
            return f"Error: Task {task_id} not found."

        if not task.runner_logs:
            return "(no logs available)"

        return task.runner_logs


BOARD_STATUSES = ["scheduled", "pending", "running", "review", "completed"]


@mcp.tool()
async def list_tasks(status: str | None = None) -> str:
    """List tasks visible on the board. Returns JSON array of {id, title, status}.

    Args:
        status: Optional filter by task status (e.g. 'scheduled', 'completed').
    """
    if status is not None and status not in BOARD_STATUSES:
        return f"Error: Invalid status '{status}'. Must be one of: {', '.join(BOARD_STATUSES)}"

    async with async_session() as session:
        if status is not None:
            if status == "completed":
                result = await session.execute(
                    select(Task).where(Task.status == status).order_by(Task.updated_at.desc())
                )
            else:
                result = await session.execute(
                    select(Task).where(Task.status == status).order_by(Task.position.asc(), Task.created_at.asc())
                )
            tasks = list(result.scalars().all())
        else:
            active = await session.execute(
                select(Task)
                .where(Task.status.not_in(["new", "deleted", "archived"]), Task.status != "completed")
                .order_by(Task.position.asc(), Task.created_at.asc())
            )
            completed = await session.execute(
                select(Task).where(Task.status == "completed").order_by(Task.updated_at.desc())
            )
            tasks = list(active.scalars().all()) + list(completed.scalars().all())

        return json.dumps([{"id": str(t.id), "title": t.title, "status": t.status} for t in tasks])


@mcp.tool()
async def schedule_task(
    description: str,
    execute_at: str,
    repeat_interval: str | None = None,
    repeat_until: str | None = None,
    profile: str | None = None,
    env: dict | None = None,
    ctx: Context | None = None,
) -> str:
    """Create a scheduled or repeating task. Optionally assign a task profile by name. Returns the task UUID.

    Args:
        description: The task description.
        execute_at: ISO 8601 datetime for when to first execute (e.g. '2026-03-01T09:00:00Z').
        repeat_interval: How often to repeat. Accepts compact format (15m, 1h, 1d, 1w) or
            human-readable (30 minutes, 2 hours, 7 days, 1 week, daily, weekly, hourly).
        repeat_until: ISO 8601 datetime for when to stop repeating (e.g. '2026-06-01T00:00:00Z').
        profile: Name of a task profile to assign.
    """
    try:
        parsed_execute_at = datetime.fromisoformat(execute_at)
    except ValueError:
        return f"Error: Invalid execute_at datetime format: '{execute_at}'. Use ISO 8601 format (e.g. '2026-03-01T09:00:00Z')."

    # Validate and normalise repeat_interval before storing
    normalised_interval = None
    if repeat_interval is not None:
        normalised_interval = normalize_interval(repeat_interval)
        if normalised_interval is None:
            return (
                f"Error: Invalid repeat_interval '{repeat_interval}'. "
                "Accepted formats: 15m, 1h, 1d, 1w, 7 days, 2 hours, daily, weekly, hourly."
            )

    parsed_repeat_until = None
    if repeat_until is not None:
        try:
            parsed_repeat_until = datetime.fromisoformat(repeat_until)
        except ValueError:
            return f"Error: Invalid repeat_until datetime format: '{repeat_until}'. Use ISO 8601 format (e.g. '2026-06-01T00:00:00Z')."

    async with async_session() as session:
        # Resolve profile name to ID
        resolved_profile_id = None
        if profile:
            prof_result = await session.execute(select(TaskProfile).where(TaskProfile.name == profile))
            found = prof_result.scalar_one_or_none()
            if not found:
                return f"Error: Task profile '{profile}' not found."
            resolved_profile_id = found.id

        words = description.strip().split()

        if len(words) > 5:
            llm_result = await generate_title(description, session)
            title = llm_result.title
            cleaned_desc = llm_result.description
        else:
            title = description.strip()
            cleaned_desc = None

        # Encrypt per-task env vars if provided
        encrypted_env, env_error = _validate_and_encrypt_env(env)
        if env_error:
            return env_error

        category = "repeating" if normalised_interval else "scheduled"
        status = "scheduled"

        result = await session.execute(
            select(func.max(Task.position)).where(Task.status == status)
        )
        max_pos = result.scalar()
        position = (max_pos or 0) + 1

        task = Task(
            title=title,
            description=cleaned_desc,
            category=category,
            status=status,
            position=position,
            execute_at=parsed_execute_at,
            repeat_interval=normalised_interval,
            repeat_until=parsed_repeat_until,
            encrypted_env=encrypted_env,
            profile_id=resolved_profile_id,
            created_by=_get_client_id(ctx),
        )
        session.add(task)
        await session.commit()
        await session.refresh(task, ["tags"])

        task_data = {
            "id": str(task.id),
            "title": task.title,
            "description": task.description,
            "status": task.status,
            "position": task.position,
            "category": task.category,
            "execute_at": task.execute_at.isoformat() if task.execute_at else None,
            "repeat_interval": task.repeat_interval,
            "repeat_until": task.repeat_until.isoformat() if task.repeat_until else None,
            "output": None,
            "runner_logs": None,
            "retry_count": 0,
            "profile_id": str(task.profile_id) if task.profile_id else None,
            "profile_name": None,
            "tags": [],
            "created_at": task.created_at.isoformat(),
            "updated_at": task.updated_at.isoformat(),
        }
        await publish_event("task_created", task_data)

        return str(task.id)


TWITTER_TCO_URL_LENGTH = 23
_TWITTER_URL_PATTERN = re.compile(r"https?://\S+")
# Trailing characters stripped from URL matches before counting. The regex
# greedily matches all non-whitespace characters, but Twitter's own URL
# detection stops before common sentence-terminating punctuation, so those
# characters should count as normal text, not as part of the t.co-shortened URL.
_URL_TRAILING_PUNCT = ".,;:!?)]}\"'"


def twitter_character_count(text: str) -> int:
    """Return the effective tweet length after Twitter's t.co URL shortening.

    All URLs matching ``https?://\\S+`` are counted as ``TWITTER_TCO_URL_LENGTH``
    characters (23), regardless of their actual length, matching Twitter's own
    behaviour of shortening every URL to a t.co link. Trailing sentence
    punctuation (``.,;:!?)]}\"'``) is stripped from matches before counting so
    that characters outside the URL are counted as normal text.
    """
    urls = [url.rstrip(_URL_TRAILING_PUNCT) for url in _TWITTER_URL_PATTERN.findall(text)]
    raw_url_chars = sum(len(url) for url in urls)
    return len(text) - raw_url_chars + TWITTER_TCO_URL_LENGTH * len(urls)


async def _load_twitter_credentials() -> dict | None:
    """Load Twitter credentials from DB, falling back to env vars. Returns None if unavailable."""
    import os
    from platforms.credentials import load_credentials

    credentials = None
    try:
        async with async_session() as session:
            credentials = await load_credentials("twitter", session)
    except Exception:
        logger.debug("Failed to load Twitter credentials from DB, trying env vars")

    if not credentials:
        api_key = os.environ.get("TWITTER_API_KEY", "")
        api_secret = os.environ.get("TWITTER_API_SECRET", "")
        access_token = os.environ.get("TWITTER_ACCESS_TOKEN", "")
        access_secret = os.environ.get("TWITTER_ACCESS_SECRET", "")

        if all([api_key, api_secret, access_token, access_secret]):
            credentials = {
                "api_key": api_key,
                "api_secret": api_secret,
                "access_token": access_token,
                "access_secret": access_secret,
            }

    return credentials


@mcp.tool()
async def post_tweet(message: str) -> str:
    """Post a tweet to Twitter/X. Message must be 1-280 characters."""
    if not message or not message.strip():
        return "Error: Message cannot be empty"

    effective_length = twitter_character_count(message)
    if effective_length > 280:
        return f"Error: Message exceeds 280 character limit (got {effective_length} characters)"

    from platforms import get_registry

    credentials = await _load_twitter_credentials()
    if not credentials:
        return "Error: Twitter API credentials not configured"

    registry = get_registry()
    platform = registry.get("twitter")
    if not platform:
        return "Error: Twitter platform not registered"

    result = await platform.post(message, credentials=credentials)
    if result.success:
        return f"Tweet posted: {result.url}"
    else:
        return f"Error posting tweet: {result.error}"


@mcp.tool()
async def reply_to_tweet(tweet_id: str, message: str) -> str:
    """Reply to a tweet by ID. Message must be 1-280 characters."""
    if not message or not message.strip():
        return "Error: Message cannot be empty"

    effective_length = twitter_character_count(message)
    if effective_length > 280:
        return f"Error: Message exceeds 280 character limit (got {effective_length} characters)"

    from platforms import get_registry

    credentials = await _load_twitter_credentials()
    if not credentials:
        return "Error: Twitter API credentials not configured"

    registry = get_registry()
    platform = registry.get("twitter")
    if not platform:
        return "Error: Twitter platform not registered"

    result = await platform.reply(tweet_id, message, credentials=credentials)
    if result.success:
        return f"Reply posted: {result.url}"
    else:
        return f"Error replying to tweet: {result.error}"


@mcp.tool()
async def like_tweet(tweet_id: str) -> str:
    """Like a tweet by ID."""
    from platforms import get_registry

    credentials = await _load_twitter_credentials()
    if not credentials:
        return "Error: Twitter API credentials not configured"

    registry = get_registry()
    platform = registry.get("twitter")
    if not platform:
        return "Error: Twitter platform not registered"

    try:
        await platform.like(tweet_id, credentials=credentials)
        return f"Liked tweet {tweet_id}"
    except Exception as e:
        return f"Error liking tweet: {e}"


@mcp.tool()
async def retweet(tweet_id: str) -> str:
    """Retweet a tweet by ID."""
    from platforms import get_registry

    credentials = await _load_twitter_credentials()
    if not credentials:
        return "Error: Twitter API credentials not configured"

    registry = get_registry()
    platform = registry.get("twitter")
    if not platform:
        return "Error: Twitter platform not registered"

    try:
        await platform.retweet(tweet_id, credentials=credentials)
        return f"Retweeted tweet {tweet_id}"
    except Exception as e:
        return f"Error retweeting: {e}"


@mcp.tool()
async def get_tweet_metrics(tweet_id: str) -> str:
    """Get metrics for a tweet by ID. Returns JSON with text, dates, and all available metric categories."""
    from platforms import get_registry

    credentials = await _load_twitter_credentials()
    if not credentials:
        return json.dumps({"error": "Twitter API credentials not configured"})

    registry = get_registry()
    platform = registry.get("twitter")
    if not platform:
        return json.dumps({"error": "Twitter platform not registered"})

    try:
        metrics = await platform.get_metrics(tweet_id, credentials=credentials)
        return json.dumps(metrics)
    except Exception as e:
        return json.dumps({"error": str(e)})


@mcp.tool()
async def get_my_recent_tweets(max_results: int = 10) -> str:
    """Get the authenticated user's recent tweets with metrics. Returns JSON array of tweets.

    Args:
        max_results: Number of tweets to return (5-100, default 10).
    """
    from platforms import get_registry

    credentials = await _load_twitter_credentials()
    if not credentials:
        return json.dumps({"error": "Twitter API credentials not configured"})

    registry = get_registry()
    platform = registry.get("twitter")
    if not platform:
        return json.dumps({"error": "Twitter platform not registered"})

    try:
        tweets = await platform.get_my_tweets(max_results, credentials=credentials)
        return json.dumps(tweets)
    except Exception as e:
        return json.dumps({"error": str(e)})


@mcp.tool()
async def search_tweets(query: str, max_results: int = 10) -> str:
    """Search recent tweets (last 7 days) by query. Requires X API Basic tier. Returns JSON array of tweets."""
    from platforms import get_registry

    credentials = await _load_twitter_credentials()
    if not credentials:
        return json.dumps({"error": "Twitter API credentials not configured"})

    registry = get_registry()
    platform = registry.get("twitter")
    if not platform:
        return json.dumps({"error": "Twitter platform not registered"})

    try:
        tweets = await platform.search(query, credentials=credentials, max_results=max_results)
        return json.dumps(tweets)
    except ValueError as e:
        return json.dumps({"error": str(e)})
    except Exception as e:
        return json.dumps({"error": str(e)})


@mcp.tool()
async def read_url(url: str, max_length: int = 50000) -> str:
    """Fetch a URL and convert its HTML content to markdown. Returns JSON with url, title, and content."""
    import re

    try:
        async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
            resp = await client.get(url)
            resp.raise_for_status()

        html_content = resp.text

        # Extract title
        title_match = re.search(r"<title[^>]*>(.*?)</title>", html_content, re.IGNORECASE | re.DOTALL)
        title = title_match.group(1).strip() if title_match else ""

        # Convert to markdown
        h = html2text.HTML2Text()
        h.ignore_links = False
        h.ignore_images = True
        h.body_width = 0
        content = h.handle(html_content)

        if len(content) > max_length:
            content = content[:max_length]

        return json.dumps({"url": url, "title": title, "content": content})
    except httpx.TimeoutException:
        return json.dumps({"error": f"Timeout fetching {url}"})
    except Exception as e:
        return json.dumps({"error": str(e)})


@mcp.tool()
async def read_rss_feed(url: str, max_items: int = 20, since: str | None = None) -> str:
    """Fetch and parse an RSS or Atom feed. Returns JSON with feed metadata and items.

    Args:
        url: The RSS or Atom feed URL to fetch.
        max_items: Maximum number of items to return (default 20).
        since: Optional ISO 8601 datetime — only return items published after this time.
    """
    import feedparser
    from datetime import datetime, timezone

    try:
        async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
            resp = await client.get(url)
            resp.raise_for_status()
    except httpx.TimeoutException:
        return json.dumps({"error": f"Timeout fetching feed from {url}"})
    except Exception as e:
        return json.dumps({"error": f"Failed to fetch feed: {e}"})

    feed = feedparser.parse(resp.text)

    if not feed.entries and not getattr(feed.feed, "title", ""):
        return json.dumps({"error": f"URL does not contain a valid RSS or Atom feed: {url}"})

    # Parse since filter
    since_dt = None
    if since:
        try:
            since_dt = datetime.fromisoformat(since.replace("Z", "+00:00"))
        except ValueError:
            return json.dumps({"error": f"Invalid 'since' datetime format: {since}"})

    # Build items
    items = []
    for entry in feed.entries:
        published = ""
        published_dt = None
        if hasattr(entry, "published_parsed") and entry.published_parsed:
            try:
                published_dt = datetime(*entry.published_parsed[:6], tzinfo=timezone.utc)
                published = published_dt.isoformat()
            except Exception:
                pass
        elif hasattr(entry, "updated_parsed") and entry.updated_parsed:
            try:
                published_dt = datetime(*entry.updated_parsed[:6], tzinfo=timezone.utc)
                published = published_dt.isoformat()
            except Exception:
                pass

        if since_dt and published_dt and published_dt <= since_dt:
            continue
        if since_dt and not published_dt:
            continue

        summary = ""
        if hasattr(entry, "summary") and entry.summary:
            summary = entry.summary[:500]
        elif hasattr(entry, "description") and entry.description:
            summary = entry.description[:500]

        items.append({
            "title": getattr(entry, "title", ""),
            "link": getattr(entry, "link", ""),
            "published": published,
            "summary": summary,
        })

    # Sort: dated items newest first, undated items last (empty string sorts before any ISO date in reverse)
    items.sort(key=lambda x: (bool(x["published"]), x["published"]), reverse=True)
    items = items[:max_items]

    feed_meta = {
        "title": getattr(feed.feed, "title", ""),
        "link": getattr(feed.feed, "link", ""),
        "description": getattr(feed.feed, "subtitle", getattr(feed.feed, "description", "")),
    }

    return json.dumps({"feed": feed_meta, "items": items})


@mcp.tool()
async def web_search(
    query: str,
    categories: str | None = None,
    time_range: str | None = None,
    language: str | None = None,
    safesearch: int | None = None,
    pageno: int | None = None,
) -> str:
    """Search the web using SearXNG. Returns JSON with results, suggestions, and result count."""
    from platforms.credentials import load_credentials
    from platforms.searxng import SearXNGPlatform, DEFAULT_URL

    credentials = None
    try:
        async with async_session() as session:
            credentials = await load_credentials("searxng", session)
    except Exception:
        logger.debug("Failed to load SearXNG credentials from DB, using default URL")

    if not credentials:
        credentials = {"url": DEFAULT_URL}

    platform = SearXNGPlatform()
    try:
        result = await platform.search(
            query,
            credentials=credentials,
            categories=categories,
            time_range=time_range,
            language=language,
            safesearch=safesearch,
            pageno=pageno,
        )
        return json.dumps(result)
    except Exception as e:
        return json.dumps({"error": str(e)})


_BLOCKED_FOLDER_NAMES = {
    "trash", "deleted", "deleted items", "deleted messages",
    "junk", "spam", "junk email",
}

# Safe IMAP search keys (RFC 3501 §6.4.4) — used to validate list_emails search param
_SAFE_IMAP_SEARCH_KEYS = {
    "ALL", "ANSWERED", "BCC", "BEFORE", "BODY", "CC", "DELETED", "DRAFT",
    "FLAGGED", "FROM", "HEADER", "KEYWORD", "LARGER", "NEW", "NOT", "OLD",
    "ON", "OR", "RECENT", "SEEN", "SENTBEFORE", "SENTON", "SENTSINCE",
    "SINCE", "SMALLER", "SUBJECT", "TEXT", "TO", "UID", "UNANSWERED",
    "UNDELETED", "UNDRAFT", "UNFLAGGED", "UNKEYWORD", "UNSEEN",
}


async def _get_email_credentials() -> dict | None:
    """Load email platform credentials from DB."""
    from platforms.credentials import load_credentials
    async with async_session() as session:
        return await load_credentials("email", session)


async def _connect_imap(creds: dict):
    """Connect and authenticate to IMAP. Returns an aioimaplib client."""
    import aioimaplib

    host = creds["imap_host"]
    port = int(creds["imap_port"])
    security = creds.get("security", "ssl")

    # Determine IMAP security from port (993=SSL, 143=STARTTLS, else follow toggle)
    use_ssl = port == 993 or (port != 143 and security == "ssl")

    if use_ssl:
        imap = aioimaplib.IMAP4_SSL(host=host, port=port)
    else:
        imap = aioimaplib.IMAP4(host=host, port=port)
    await imap.wait_hello_from_server()

    if not use_ssl:
        await imap.starttls()

    await imap.login(creds["username"], creds["password"])
    return imap


def _is_blocked_folder(folder_name: str, folder_attributes: list[str] | None = None) -> bool:
    """Check if a folder is blocked (trash/junk/spam)."""
    # Extract final path component
    final = folder_name.rsplit("/", 1)[-1].rsplit(".", 1)[-1]
    if final.lower() in _BLOCKED_FOLDER_NAMES:
        return True
    # Check SPECIAL-USE attributes
    if folder_attributes:
        for attr in folder_attributes:
            if attr.lower() in ("\\trash", "\\junk"):
                return True
    return False


def _get_authorized_recipients(creds: dict) -> list[str]:
    """Parse authorized_recipients from credentials (newline-separated)."""
    raw = creds.get("authorized_recipients", "")
    if not raw or not raw.strip():
        return []
    return [addr.strip().lower() for addr in raw.strip().splitlines() if addr.strip()]


def _email_body_to_markdown(raw_bytes: bytes) -> str:
    """Convert email body to markdown."""
    import html2text
    from email import policy

    msg = email_module.message_from_bytes(raw_bytes, policy=policy.default)
    html_part = None
    text_part = None

    if msg.is_multipart():
        for part in msg.walk():
            ct = part.get_content_type()
            if ct == "text/html" and html_part is None:
                html_part = part.get_content()
            elif ct == "text/plain" and text_part is None:
                text_part = part.get_content()
    else:
        ct = msg.get_content_type()
        if ct == "text/html":
            html_part = msg.get_content()
        elif ct == "text/plain":
            text_part = msg.get_content()

    if html_part:
        h = html2text.HTML2Text()
        h.ignore_links = False
        h.ignore_images = True
        h.body_width = 0
        return h.handle(html_part)
    return text_part or ""


def _extract_attachments(raw_bytes: bytes) -> list[dict]:
    """Extract attachment metadata from raw email bytes."""
    from email import policy

    msg = email_module.message_from_bytes(raw_bytes, policy=policy.default)
    attachments = []
    if msg.is_multipart():
        for part in msg.walk():
            cd = part.get("Content-Disposition", "")
            if "attachment" in cd:
                filename = part.get_filename() or "unnamed"
                content_type = part.get_content_type()
                payload = part.get_payload(decode=True)
                size = len(payload) if payload else 0
                attachments.append({
                    "filename": filename,
                    "content_type": content_type,
                    "size": size,
                })
    return attachments


@mcp.tool()
async def list_emails(folder: str = "INBOX", limit: int = 20, search: str | None = None) -> str:
    """List email messages from a folder. Returns JSON with message summaries."""
    creds = await _get_email_credentials()
    if not creds:
        return json.dumps({"error": "Email platform not configured"})

    try:
        imap = await _connect_imap(creds)
        try:
            await imap.select(folder)

            if search:
                # Validate search keys against RFC 3501 safe set to prevent injection
                tokens = search.split()
                for token in tokens:
                    # Skip quoted string values (arguments to search keys like FROM "addr")
                    if token.startswith('"') or token.isdigit() or ":" in token:
                        continue
                    if token.upper() not in _SAFE_IMAP_SEARCH_KEYS:
                        return json.dumps({"error": f"Unsupported IMAP search key: {token}"})
                response = await imap.search(search)
            else:
                response = await imap.search("ALL")

            if response.result != "OK":
                return json.dumps({"error": f"Search failed: {response.lines}"})

            uid_line = response.lines[0]
            if not uid_line or not uid_line.strip():
                return json.dumps({"messages": []})

            uids = uid_line.strip().split()
            if isinstance(uids[0], bytes):
                uids = [u.decode() for u in uids]
            # Take last N messages (most recent)
            uids = uids[-limit:]

            messages = []
            for uid in uids:
                fetch_resp = await imap.fetch(uid, "(UID FLAGS RFC822.HEADER)")
                if fetch_resp.result != "OK":
                    continue

                # Extract header bytes and flags from response
                from email import policy
                header_bytes = None
                flags_str = ""
                for line in fetch_resp.lines:
                    if isinstance(line, bytearray) and len(line) > 0:
                        header_bytes = bytes(line)
                    elif isinstance(line, bytes) and len(line) > 0:
                        if header_bytes is None or len(line) > len(header_bytes):
                            header_bytes = line
                    elif isinstance(line, str) and "FLAGS" in line:
                        flags_str = line

                if header_bytes:
                    msg = email_module.message_from_bytes(header_bytes, policy=policy.default)
                    messages.append({
                        "uid": uid,
                        "from": str(msg.get("From", "")),
                        "to": str(msg.get("To", "")),
                        "subject": str(msg.get("Subject", "")),
                        "date": str(msg.get("Date", "")),
                        "unread": "\\Seen" not in flags_str,
                        "flags": flags_str,
                    })
                else:
                    messages.append({"uid": uid, "summary": "Failed to parse headers"})

            return json.dumps({"messages": messages})
        finally:
            try:
                await imap.logout()
            except Exception:
                pass
    except Exception as e:
        return json.dumps({"error": str(e)})


@mcp.tool()
async def read_email(message_uid: str, folder: str = "INBOX") -> str:
    """Read a full email message by UID. Returns JSON with headers, markdown body, and attachment metadata."""
    creds = await _get_email_credentials()
    if not creds:
        return json.dumps({"error": "Email platform not configured"})

    try:
        imap = await _connect_imap(creds)
        try:
            await imap.select(folder)
            fetch_resp = await imap.fetch(message_uid, "(RFC822)")
            if fetch_resp.result != "OK":
                return json.dumps({"error": f"Message {message_uid} not found"})

            raw_email = None
            for line in fetch_resp.lines:
                if isinstance(line, bytearray) and len(line) > 0:
                    raw_email = bytes(line)
                    break
                elif isinstance(line, bytes) and len(line) > 0:
                    if raw_email is None or len(line) > len(raw_email):
                        raw_email = line

            if raw_email is None:
                return json.dumps({"error": f"Message {message_uid} not found"})

            from email import policy
            msg = email_module.message_from_bytes(raw_email, policy=policy.default)

            body = _email_body_to_markdown(raw_email)
            attachments = _extract_attachments(raw_email)

            return json.dumps({
                "uid": message_uid,
                "from": str(msg.get("From", "")),
                "to": str(msg.get("To", "")),
                "cc": str(msg.get("Cc", "")),
                "subject": str(msg.get("Subject", "")),
                "date": str(msg.get("Date", "")),
                "body": body,
                "attachments": attachments,
            })
        finally:
            try:
                await imap.logout()
            except Exception:
                pass
    except Exception as e:
        return json.dumps({"error": str(e)})


@mcp.tool()
async def list_email_folders() -> str:
    """List all email folders. Returns JSON with folder names and attributes."""
    creds = await _get_email_credentials()
    if not creds:
        return json.dumps({"error": "Email platform not configured"})

    try:
        imap = await _connect_imap(creds)
        try:
            response = await imap.list('""', '"*"')
            if response.result != "OK":
                return json.dumps({"error": f"LIST failed: {response.lines}"})

            folders = []
            import re
            for line in response.lines:
                if not line:
                    continue
                line_str = line.decode() if isinstance(line, bytes) else str(line)
                # Parse IMAP LIST response: (attributes) "delimiter" "name"
                match = re.match(r'\(([^)]*)\)\s+"(.+?)"\s+"?(.+?)"?\s*$', line_str)
                if match:
                    attrs = match.group(1).split()
                    delimiter = match.group(2)
                    name = match.group(3).strip('"')
                    folders.append({
                        "name": name,
                        "attributes": attrs,
                        "delimiter": delimiter,
                    })

            return json.dumps({"folders": folders})
        finally:
            try:
                await imap.logout()
            except Exception:
                pass
    except Exception as e:
        return json.dumps({"error": str(e)})


@mcp.tool()
async def move_email(message_uid: str, folder: str, source_folder: str = "INBOX") -> str:
    """Move an email to a different folder. Returns JSON indicating success or error."""
    creds = await _get_email_credentials()
    if not creds:
        return json.dumps({"error": "Email platform not configured"})

    # Check blocked folder with name-based detection
    if _is_blocked_folder(folder):
        return json.dumps({"error": f"Cannot move to {folder} — deletion is not permitted"})

    try:
        imap = await _connect_imap(creds)
        try:
            # Also check SPECIAL-USE attributes for the target folder
            response = await imap.list('""', f'"{folder}"')
            if response.result == "OK":
                import re
                for line in response.lines:
                    if not line:
                        continue
                    line_str = line.decode() if isinstance(line, bytes) else str(line)
                    match = re.match(r'\(([^)]*)\)', line_str)
                    if match:
                        attrs = match.group(1).split()
                        if _is_blocked_folder(folder, attrs):
                            return json.dumps({"error": f"Cannot move to {folder} — deletion is not permitted"})

            await imap.select(source_folder)

            # Create target folder if it doesn't exist (ignore error if exists)
            try:
                await imap.create(folder)
            except Exception:
                pass

            # COPY to target
            copy_resp = await imap.copy(message_uid, folder)
            if copy_resp.result != "OK":
                return json.dumps({"error": f"COPY failed: {copy_resp.lines}"})

            # Mark as deleted + expunge from source
            await imap.store(message_uid, "+FLAGS", "\\Deleted")
            await imap.expunge()

            return json.dumps({"success": True, "message": f"Moved to {folder}"})
        finally:
            try:
                await imap.logout()
            except Exception:
                pass
    except Exception as e:
        return json.dumps({"error": str(e)})


@mcp.tool()
async def send_email(to: str, subject: str, body: str) -> str:
    """Send an email to an authorised recipient. Returns JSON indicating success or error."""
    import aiosmtplib

    creds = await _get_email_credentials()
    if not creds:
        return json.dumps({"error": "Email platform not configured"})

    authorized = _get_authorized_recipients(creds)
    if not authorized:
        return json.dumps({"error": "No recipients are authorised"})

    if to.strip().lower() not in authorized:
        return json.dumps({"error": "Recipient not in authorised recipients list"})

    try:
        msg = EmailMessage()
        msg["From"] = creds["username"]
        msg["To"] = to
        msg["Subject"] = subject
        msg.set_content(body)

        smtp_host = creds["smtp_host"]
        smtp_port = int(creds["smtp_port"])
        security = creds.get("security", "ssl")
        # Determine SMTP security from port (465=SSL, 587/25=STARTTLS, else follow toggle)
        smtp_use_ssl = smtp_port == 465 or (smtp_port not in (587, 25) and security == "ssl")

        smtp = aiosmtplib.SMTP(hostname=smtp_host, port=smtp_port, use_tls=smtp_use_ssl, start_tls=not smtp_use_ssl)
        await smtp.connect()
        try:
            await smtp.login(creds["username"], creds["password"])
            await smtp.send_message(msg)
        finally:
            try:
                await smtp.quit()
            except Exception:
                pass

        return json.dumps({"success": True, "message": "Email sent"})
    except Exception as e:
        return json.dumps({"error": str(e)})


@mcp.tool()
async def forward_email(message_uid: str, to: str, folder: str = "INBOX") -> str:
    """Forward an email to an authorised recipient. Returns JSON indicating success or error."""
    import aiosmtplib

    creds = await _get_email_credentials()
    if not creds:
        return json.dumps({"error": "Email platform not configured"})

    authorized = _get_authorized_recipients(creds)
    if not authorized:
        return json.dumps({"error": "No recipients are authorised"})

    if to.strip().lower() not in authorized:
        return json.dumps({"error": "Recipient not in authorised recipients list"})

    try:
        # Fetch original message
        imap = await _connect_imap(creds)
        try:
            await imap.select(folder)
            fetch_resp = await imap.fetch(message_uid, "(RFC822)")
            if fetch_resp.result != "OK":
                return json.dumps({"error": f"Message {message_uid} not found"})

            raw_email = None
            for line in fetch_resp.lines:
                if isinstance(line, bytearray) and len(line) > 0:
                    raw_email = bytes(line)
                    break
                elif isinstance(line, bytes) and len(line) > 0:
                    if raw_email is None or len(line) > len(raw_email):
                        raw_email = line

            if raw_email is None:
                return json.dumps({"error": f"Message {message_uid} not found"})
        finally:
            try:
                await imap.logout()
            except Exception:
                pass

        from email import policy
        original = email_module.message_from_bytes(raw_email, policy=policy.default)
        orig_from = str(original.get("From", ""))
        orig_to = str(original.get("To", ""))
        orig_date = str(original.get("Date", ""))
        orig_subject = str(original.get("Subject", ""))
        orig_body = _email_body_to_markdown(raw_email)

        fwd_body = (
            f"---------- Forwarded message ----------\n"
            f"From: {orig_from}\n"
            f"Date: {orig_date}\n"
            f"Subject: {orig_subject}\n"
            f"To: {orig_to}\n\n"
            f"{orig_body}"
        )

        msg = EmailMessage()
        msg["From"] = creds["username"]
        msg["To"] = to
        msg["Subject"] = f"Fwd: {orig_subject}"
        msg.set_content(fwd_body)

        smtp_host = creds["smtp_host"]
        smtp_port = int(creds["smtp_port"])
        security = creds.get("security", "ssl")
        # Determine SMTP security from port (465=SSL, 587/25=STARTTLS, else follow toggle)
        smtp_use_ssl = smtp_port == 465 or (smtp_port not in (587, 25) and security == "ssl")

        smtp = aiosmtplib.SMTP(hostname=smtp_host, port=smtp_port, use_tls=smtp_use_ssl, start_tls=not smtp_use_ssl)
        await smtp.connect()
        try:
            await smtp.login(creds["username"], creds["password"])
            await smtp.send_message(msg)
        finally:
            try:
                await smtp.quit()
            except Exception:
                pass

        return json.dumps({"success": True, "message": "Email forwarded"})
    except Exception as e:
        return json.dumps({"error": str(e)})


def create_mcp_app() -> Starlette:
    """Create the MCP Starlette app for mounting on the main FastAPI app.

    Also initializes mcp._session_manager as a side effect.
    The caller must run `mcp.session_manager.run()` in the app lifespan
    because Starlette 0.38.x does not propagate lifespans to mounted sub-apps.
    """
    return mcp.streamable_http_app()
