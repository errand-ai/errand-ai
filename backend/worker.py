import asyncio
import io
import json
import logging
import re
import os
import signal
import tarfile
import time
from datetime import datetime, timedelta, timezone
from typing import Literal, Optional

import docker
from docker.errors import DockerException, APIError, ImageNotFound
from pydantic import BaseModel, ValidationError
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from database import async_session, engine
from events import init_valkey, close_valkey, publish_event
from models import Setting, Skill, Tag, Task, task_tags


class TaskRunnerOutput(BaseModel):
    status: Literal["completed", "needs_input"]
    result: str
    questions: list[str] = []


def extract_json(text: str) -> str | None:
    """Extract a valid TaskRunnerOutput JSON string from LLM output.

    Tries three strategies in order:
    1. Direct parse of the full text
    2. Extract content from a markdown code fence anywhere in text
    3. Extract substring from first '{' to last '}'

    Returns the JSON string if valid TaskRunnerOutput, otherwise None.
    """
    stripped = text.strip()

    # Strategy 1: direct parse
    try:
        TaskRunnerOutput.model_validate_json(stripped)
        return stripped
    except (ValidationError, ValueError):
        pass

    # Strategy 2: code fence extraction
    fence_match = re.search(r"```(?:json)?\s*\n(.*?)\n\s*```", stripped, re.DOTALL)
    if fence_match:
        fenced_content = fence_match.group(1).strip()
        try:
            TaskRunnerOutput.model_validate_json(fenced_content)
            return fenced_content
        except (ValidationError, ValueError):
            pass

    # Strategy 3: first '{' to last '}'
    first_brace = stripped.find("{")
    last_brace = stripped.rfind("}")
    if first_brace != -1 and last_brace > first_brace:
        brace_content = stripped[first_brace:last_brace + 1]
        try:
            TaskRunnerOutput.model_validate_json(brace_content)
            return brace_content
        except (ValidationError, ValueError):
            pass

    return None


logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

POLL_INTERVAL = int(os.environ.get("POLL_INTERVAL", "5"))
DOCKER_HOST = os.environ.get("DOCKER_HOST", "")
TASK_RUNNER_IMAGE = os.environ.get("TASK_RUNNER_IMAGE", "content-manager-task-runner:latest")
MAX_OUTPUT_BYTES = int(os.environ.get("MAX_OUTPUT_BYTES", str(1024 * 1024)))  # 1MB default

shutdown_requested = False
shutdown_event: Optional[asyncio.Event] = None
docker_client: Optional[docker.DockerClient] = None
active_container_id: Optional[str] = None


def handle_sigterm(*_args):
    global shutdown_requested
    logger.info("SIGTERM received, finishing current task before shutdown")
    shutdown_requested = True
    if shutdown_event is not None:
        loop = asyncio.get_event_loop()
        loop.call_soon_threadsafe(shutdown_event.set)
    # Stop and remove any running container
    _cleanup_active_container()


def _cleanup_active_container():
    global active_container_id
    if docker_client is not None and active_container_id is not None:
        try:
            container = docker_client.containers.get(active_container_id)
            container.stop(timeout=5)
            container.remove(force=True)
            logger.info("Cleaned up container %s on shutdown", active_container_id)
        except Exception:
            pass
        active_container_id = None


def init_docker_client() -> docker.DockerClient:
    """Initialise Docker client with exponential backoff retry waiting for DinD readiness."""
    delay = 1.0
    max_delay = 30.0
    kwargs = {}
    if DOCKER_HOST:
        kwargs["base_url"] = DOCKER_HOST

    while True:
        try:
            client = docker.DockerClient(**kwargs)
            client.ping()
            logger.info("Connected to Docker daemon")
            return client
        except DockerException as e:
            logger.warning("Docker not ready (%.1fs backoff): %s", delay, e)
            time.sleep(delay)
            delay = min(delay * 2, max_delay)


def put_archive(container, files: dict[str, str], dest: str = "/workspace") -> None:
    """Create a tar archive from a dict of {filename: content} and copy into container."""
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w") as tar:
        for name, content in files.items():
            data = content.encode("utf-8")
            info = tarfile.TarInfo(name=name)
            info.size = len(data)
            tar.addfile(info, io.BytesIO(data))
    buf.seek(0)
    container.put_archive(dest, buf)


def build_skills_archive(skills: list[dict]) -> bytes | None:
    """Build a tar archive containing Agent Skills directories.

    Each skill becomes a directory with SKILL.md (YAML frontmatter + instructions body)
    and optional files in scripts/, references/, assets/ subdirectories.
    Returns the tar bytes, or None if no skills exist.
    """
    if not skills:
        return None

    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w") as tar:
        for skill in skills:
            name = skill["name"]
            description = skill.get("description", "")
            instructions = skill.get("instructions", "")

            # Build SKILL.md content with YAML frontmatter
            skill_md = f"---\nname: {name}\ndescription: {description}\n---\n\n{instructions}"
            data = skill_md.encode("utf-8")
            info = tarfile.TarInfo(name=f"skills/{name}/SKILL.md")
            info.size = len(data)
            tar.addfile(info, io.BytesIO(data))

            # Add attached files
            for f in skill.get("files", []):
                file_data = f["content"].encode("utf-8")
                file_info = tarfile.TarInfo(name=f"skills/{name}/{f['path']}")
                file_info.size = len(file_data)
                tar.addfile(file_info, io.BytesIO(file_data))

    buf.seek(0)
    return buf.getvalue()


def build_skill_manifest(skills: list[dict]) -> str:
    """Build the system prompt skill manifest section."""
    lines = [
        "\n\n## Skills\n",
        "Available skills are installed at /workspace/skills/. Each skill directory contains a SKILL.md file with full instructions, and may include scripts/, references/, and assets/ subdirectories.\n",
        "| Skill | Description |",
        "|-------|-------------|",
    ]
    for skill in skills:
        lines.append(f"| {skill['name']} | {skill.get('description', '')} |")
    lines.append("")
    lines.append("If a skill is relevant to your task, read its SKILL.md file to load the full instructions before proceeding.")
    return "\n".join(lines)


def truncate_output(output: str, max_bytes: int = MAX_OUTPUT_BYTES) -> str:
    """Truncate output to max_bytes, appending a marker if exceeded."""
    encoded = output.encode("utf-8")
    if len(encoded) <= max_bytes:
        return output
    truncated = encoded[:max_bytes].decode("utf-8", errors="ignore")
    return truncated + "\n\n--- OUTPUT TRUNCATED (exceeded %d bytes) ---" % max_bytes


DEFAULT_TASK_PROCESSING_MODEL = "claude-sonnet-4-5-20250929"


async def read_settings(session: AsyncSession) -> dict:
    """Read task processing settings from the settings table and skills from the skills table.

    Returns a dict with keys: mcp_servers, credentials, task_processing_model, system_prompt, task_runner_log_level, skills.
    """
    settings: dict = {
        "mcp_servers": {},
        "credentials": [],
        "task_processing_model": DEFAULT_TASK_PROCESSING_MODEL,
        "system_prompt": "",
        "task_runner_log_level": "",
        "skills": [],
        "mcp_api_key": "",
        "ssh_private_key": "",
        "git_ssh_hosts": [],
    }

    result = await session.execute(
        select(Setting).where(
            Setting.key.in_(["mcp_servers", "credentials", "task_processing_model", "system_prompt", "task_runner_log_level", "mcp_api_key", "ssh_private_key", "git_ssh_hosts"])
        )
    )
    for setting in result.scalars().all():
        if setting.key == "mcp_servers":
            settings["mcp_servers"] = setting.value if isinstance(setting.value, dict) else {}
        elif setting.key == "credentials":
            settings["credentials"] = setting.value if isinstance(setting.value, list) else []
        elif setting.key == "task_processing_model":
            settings["task_processing_model"] = str(setting.value) if setting.value else DEFAULT_TASK_PROCESSING_MODEL
        elif setting.key == "system_prompt":
            settings["system_prompt"] = str(setting.value) if setting.value else ""
        elif setting.key == "task_runner_log_level":
            settings["task_runner_log_level"] = str(setting.value) if setting.value else ""
        elif setting.key == "mcp_api_key":
            settings["mcp_api_key"] = str(setting.value) if setting.value else ""
        elif setting.key == "ssh_private_key":
            settings["ssh_private_key"] = str(setting.value) if setting.value else ""
        elif setting.key == "git_ssh_hosts":
            settings["git_ssh_hosts"] = setting.value if isinstance(setting.value, list) else []

    # Query skills from dedicated tables
    skill_result = await session.execute(
        select(Skill).options(selectinload(Skill.files)).order_by(Skill.name)
    )
    skills_list = []
    for skill in skill_result.scalars().all():
        skills_list.append({
            "name": skill.name,
            "description": skill.description,
            "instructions": skill.instructions,
            "files": [{"path": f.path, "content": f.content} for f in skill.files],
        })
    settings["skills"] = skills_list

    return settings


async def dequeue_task(session: AsyncSession) -> Task | None:
    result = await session.execute(
        select(Task)
        .options(selectinload(Task.tags))
        .where(Task.status == "pending")
        .order_by(Task.position.asc(), Task.created_at.asc())
        .limit(1)
        .with_for_update(skip_locked=True)
    )
    return result.scalar_one_or_none()


def parse_interval(interval_str: str) -> timedelta | None:
    """Parse simple duration strings (15m, 1h, 1d, 1w) into timedelta objects.

    Returns None for unparseable formats (e.g. crontab expressions).
    """
    match = re.fullmatch(r"(\d+)([mhdw])", interval_str.strip())
    if not match:
        return None
    value, unit = int(match.group(1)), match.group(2)
    if unit == "m":
        return timedelta(minutes=value)
    if unit == "h":
        return timedelta(hours=value)
    if unit == "d":
        return timedelta(days=value)
    if unit == "w":
        return timedelta(weeks=value)
    return None



def _task_to_dict(task: Task) -> dict:
    return {
        "id": str(task.id),
        "title": task.title,
        "description": task.description,
        "status": task.status,
        "position": task.position,
        "category": task.category,
        "execute_at": task.execute_at.isoformat() if task.execute_at else None,
        "repeat_interval": task.repeat_interval,
        "repeat_until": task.repeat_until.isoformat() if task.repeat_until else None,
        "output": task.output,
        "runner_logs": task.runner_logs,
        "retry_count": task.retry_count,
        "tags": sorted([t.name for t in task.tags]),
        "created_at": task.created_at.isoformat() if task.created_at else None,
        "updated_at": task.updated_at.isoformat() if task.updated_at else None,
    }


async def _next_position(session: AsyncSession, status: str) -> int:
    """Return the next position value for a task in the given status column."""
    result = await session.execute(
        select(func.max(Task.position)).where(Task.status == status)
    )
    max_pos = result.scalar()
    return (max_pos or 0) + 1


_ENV_VAR_RE = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)\}|\$([A-Za-z_][A-Za-z0-9_]*)")


def substitute_env_vars(obj, environ=None):
    """Recursively substitute $VAR and ${VAR} placeholders in string values."""
    if environ is None:
        environ = os.environ

    def _replace_match(m):
        var_name = m.group(1) or m.group(2)
        return environ.get(var_name, m.group(0))

    if isinstance(obj, str):
        return _ENV_VAR_RE.sub(_replace_match, obj)
    if isinstance(obj, dict):
        return {k: substitute_env_vars(v, environ) for k, v in obj.items()}
    if isinstance(obj, list):
        return [substitute_env_vars(item, environ) for item in obj]
    return obj


def generate_ssh_config(hosts: list[str]) -> str:
    """Generate an SSH config file with per-host entries for git SSH authentication."""
    entries = []
    for host in hosts:
        entries.append(
            f"Host {host}\n"
            f"    IdentityFile ~/.ssh/id_rsa.agent\n"
            f"    User git\n"
            f"    StrictHostKeyChecking accept-new"
        )
    return "\n\n".join(entries) + "\n" if entries else ""


def put_archive_ssh(container, private_key: str, ssh_config: str) -> None:
    """Copy SSH private key and config into the container's ~/.ssh/ directory."""
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w") as tar:
        # .ssh directory entry — ensures permissions are 700 (SSH requires this)
        ssh_dir = tarfile.TarInfo(name=".")
        ssh_dir.type = tarfile.DIRTYPE
        ssh_dir.mode = 0o700
        ssh_dir.uid = 65532
        ssh_dir.gid = 65532
        tar.addfile(ssh_dir)

        # Private key with permissions 600
        key_data = private_key.encode("utf-8")
        key_info = tarfile.TarInfo(name="id_rsa.agent")
        key_info.size = len(key_data)
        key_info.mode = 0o600
        key_info.uid = 65532
        key_info.gid = 65532
        tar.addfile(key_info, io.BytesIO(key_data))

        # SSH config with permissions 644
        config_data = ssh_config.encode("utf-8")
        config_info = tarfile.TarInfo(name="config")
        config_info.size = len(config_data)
        config_info.mode = 0o644
        config_info.uid = 65532
        config_info.gid = 65532
        tar.addfile(config_info, io.BytesIO(config_data))
    buf.seek(0)
    container.put_archive("/home/nonroot/.ssh", buf)


def process_task_in_container(task: Task, settings: dict) -> tuple[int, str, str]:
    """Run task in a Docker container via DinD. Returns (exit_code, stdout, stderr)."""
    global active_container_id

    mcp_servers = settings.get("mcp_servers", {})
    credentials = settings.get("credentials", [])
    task_processing_model = settings.get("task_processing_model", DEFAULT_TASK_PROCESSING_MODEL)
    system_prompt = settings.get("system_prompt", "")

    # Build environment variables from credentials
    env_vars = {}
    for cred in credentials:
        if isinstance(cred, dict) and "key" in cred and "value" in cred:
            env_vars[cred["key"]] = cred["value"]

    # Add task runner env vars
    openai_base_url = os.environ.get("OPENAI_BASE_URL", "")
    openai_api_key = os.environ.get("OPENAI_API_KEY", "")
    if openai_base_url:
        env_vars["OPENAI_BASE_URL"] = openai_base_url
    if openai_api_key:
        env_vars["OPENAI_API_KEY"] = openai_api_key
    env_vars["OPENAI_MODEL"] = task_processing_model
    env_vars["USER_PROMPT_PATH"] = "/workspace/prompt.txt"
    env_vars["SYSTEM_PROMPT_PATH"] = "/workspace/system_prompt.txt"
    env_vars["MCP_CONFIGURATION_PATH"] = "/workspace/mcp.json"
    task_runner_log_level = settings.get("task_runner_log_level") or os.environ.get("TASK_RUNNER_LOG_LEVEL", "")
    if task_runner_log_level:
        env_vars["LOG_LEVEL"] = task_runner_log_level

    # Ensure image is available (try local first, pull only if not found)
    try:
        docker_client.images.get(TASK_RUNNER_IMAGE)
        logger.info("Image %s found locally", TASK_RUNNER_IMAGE)
    except ImageNotFound:
        logger.info("Image %s not found locally, pulling...", TASK_RUNNER_IMAGE)
        docker_client.images.pull(TASK_RUNNER_IMAGE)

    # Create container (not started)
    container = docker_client.containers.create(
        image=TASK_RUNNER_IMAGE,
        environment=env_vars,
        network_mode="host",
        detach=True,
    )
    active_container_id = container.id
    logger.info("Created container %s for task %s", container.short_id, task.id)

    try:
        # Inject Perplexity MCP server if enabled via environment
        if os.environ.get("USE_PERPLEXITY") == "true":
            mcp_servers.setdefault("mcpServers", {})
            if "perplexity-ask" not in mcp_servers["mcpServers"]:
                mcp_servers["mcpServers"]["perplexity-ask"] = {"url": "$PERPLEXITY_URL"}
            system_prompt += (
                "\n\n## Perplexity Web Search\n\n"
                "You have access to the `perplexity-ask` MCP tool. Use it to look up "
                "current information online, conduct web research, or reason about "
                "topics that require context beyond your training data."
            )

        # Inject content-manager MCP server for task tools (post_tweet, new_task, etc.)
        backend_mcp_url = os.environ.get("BACKEND_MCP_URL", "")
        mcp_api_key = settings.get("mcp_api_key", "")
        if backend_mcp_url and mcp_api_key:
            mcp_servers.setdefault("mcpServers", {})
            if "content-manager" not in mcp_servers["mcpServers"]:
                mcp_servers["mcpServers"]["content-manager"] = {
                    "url": backend_mcp_url,
                    "headers": {"Authorization": f"Bearer {mcp_api_key}"},
                }

        # Inject skill manifest into system prompt if skills are defined
        skills = settings.get("skills", [])
        if skills:
            system_prompt += build_skill_manifest(skills)

        # Copy files into the stopped container
        prompt_text = task.description or task.title
        files = {
            "prompt.txt": prompt_text,
            "system_prompt.txt": system_prompt,
            "mcp.json": json.dumps(substitute_env_vars(mcp_servers)),
        }
        put_archive(container, files)

        # Write Agent Skills directories into the container
        if skills:
            skills_tar = build_skills_archive(skills)
            if skills_tar:
                container.put_archive("/workspace", io.BytesIO(skills_tar))
                logger.info("Injected %d skill(s) into container for task %s", len(skills), task.id)

        # Inject SSH credentials if available
        ssh_private_key = settings.get("ssh_private_key", "")
        if ssh_private_key:
            git_ssh_hosts = settings.get("git_ssh_hosts", [])
            ssh_config = generate_ssh_config(git_ssh_hosts)
            put_archive_ssh(container, ssh_private_key, ssh_config)
            logger.info("Injected SSH credentials for task %s (%d hosts)", task.id, len(git_ssh_hosts))

        # Start and wait
        container.start()
        result = container.wait()
        exit_code = result.get("StatusCode", -1)

        # Capture stdout (structured JSON) and stderr (logs) separately
        stdout = container.logs(stdout=True, stderr=False).decode("utf-8", errors="replace")
        stderr = container.logs(stdout=False, stderr=True).decode("utf-8", errors="replace")
        stdout = truncate_output(stdout)
        stderr = truncate_output(stderr)

        return exit_code, stdout, stderr
    finally:
        try:
            container.remove(force=True)
        except Exception:
            pass
        active_container_id = None


async def _schedule_retry(task: Task, output: str | None = None, runner_logs: str | None = None) -> None:
    """Move a failed task back to scheduled with exponential backoff on execute_at."""
    async with async_session() as session:
        # Read current retry_count from DB (task object may be stale)
        result = await session.execute(select(Task).where(Task.id == task.id))
        current = result.scalar_one()
        new_retry = current.retry_count + 1
        backoff_minutes = 2 ** (current.retry_count)  # 1, 2, 4, 8, 16, ...
        execute_at = datetime.now(timezone.utc) + timedelta(minutes=backoff_minutes)
        new_position = await _next_position(session, "scheduled")

        values = {
            "status": "scheduled",
            "position": new_position,
            "retry_count": new_retry,
            "execute_at": execute_at,
            "updated_at": datetime.now(timezone.utc),
        }
        if output is not None:
            values["output"] = output
        if runner_logs is not None:
            values["runner_logs"] = runner_logs

        await session.execute(
            update(Task).where(Task.id == task.id).values(**values)
        )

        # Add "Retry" tag to task (find-or-create, guard against duplicates)
        result = await session.execute(
            select(Tag).where(Tag.name == "Retry")
        )
        retry_tag = result.scalar_one_or_none()
        if retry_tag is None:
            retry_tag = Tag(name="Retry")
            session.add(retry_tag)
            await session.flush()
        existing = await session.execute(
            select(task_tags).where(
                task_tags.c.task_id == task.id,
                task_tags.c.tag_id == retry_tag.id,
            )
        )
        if existing.first() is None:
            await session.execute(
                task_tags.insert().values(task_id=task.id, tag_id=retry_tag.id)
            )

        await session.commit()
        result = await session.execute(
            select(Task).options(selectinload(Task.tags)).where(Task.id == task.id)
        )
        retried_task = result.scalar_one()
        await publish_event("task_updated", _task_to_dict(retried_task))
        logger.info(
            "Task %s scheduled for retry %d in %d min (execute_at=%s)",
            task.id, new_retry, backoff_minutes, execute_at.isoformat(),
        )


async def _reschedule_if_repeating(task: Task) -> None:
    """If the task is repeating and not expired, create a cloned task for the next interval."""
    if task.category != "repeating":
        return

    if task.repeat_until and datetime.now(timezone.utc) > task.repeat_until:
        logger.info("Task %s: repeat_until has passed, not rescheduling", task.id)
        return

    interval = parse_interval(task.repeat_interval or "")
    if interval is None:
        logger.warning(
            "Task %s: cannot parse repeat_interval '%s', skipping reschedule",
            task.id, task.repeat_interval,
        )
        return

    async with async_session() as session:
        position = await _next_position(session, "scheduled")
        new_task = Task(
            title=task.title,
            description=task.description,
            status="scheduled",
            category=task.category,
            execute_at=datetime.now(timezone.utc) + interval,
            repeat_interval=task.repeat_interval,
            repeat_until=task.repeat_until,
            position=position,
            output=None,
            runner_logs=None,
            retry_count=0,
        )
        session.add(new_task)
        await session.flush()

        # Copy tags from completed task to new task
        for tag in task.tags:
            await session.execute(
                task_tags.insert().values(task_id=new_task.id, tag_id=tag.id)
            )

        await session.commit()

        # Load with tags for WebSocket event
        result = await session.execute(
            select(Task).options(selectinload(Task.tags)).where(Task.id == new_task.id)
        )
        new_task_loaded = result.scalar_one()
        await publish_event("task_created", _task_to_dict(new_task_loaded))
        logger.info("Task %s: rescheduled as new task %s", task.id, new_task.id)


async def run() -> None:
    global shutdown_event, docker_client
    shutdown_event = asyncio.Event()

    signal.signal(signal.SIGTERM, handle_sigterm)
    await init_valkey()

    # Initialise Docker client (blocking, with retry)
    logger.info("Connecting to Docker daemon...")
    docker_client = await asyncio.get_event_loop().run_in_executor(None, init_docker_client)

    logger.info("Worker started, polling every %ds", POLL_INTERVAL)

    while not shutdown_requested:
        async with async_session() as session:
            task = await dequeue_task(session)
            if task is None:
                await session.close()
                if shutdown_requested:
                    break
                try:
                    await asyncio.wait_for(shutdown_event.wait(), timeout=POLL_INTERVAL)
                except TimeoutError:
                    pass
                continue

            # Read settings for this task
            settings = await read_settings(session)

            # Set status to running
            task.status = "running"
            await session.commit()
            await session.refresh(task)
            await publish_event("task_updated", _task_to_dict(task))

        # Process outside the dequeue transaction
        try:
            exit_code, stdout, stderr = await asyncio.get_event_loop().run_in_executor(
                None, process_task_in_container, task, settings
            )
            # Combine for display/storage; use stdout only for parsing
            full_output = (stderr + "\n" + stdout).strip() if stderr else stdout

            if exit_code == 0:
                # Extract structured JSON from stdout (handles preamble text, code fences, etc.)
                clean_stdout = extract_json(stdout)
                if clean_stdout is None:
                    logger.warning("Task %s: failed to extract structured output from stdout", task.id)
                    await _schedule_retry(task, output=full_output, runner_logs=stderr)
                    continue

                try:
                    parsed = TaskRunnerOutput.model_validate_json(clean_stdout)
                except (ValidationError, ValueError) as e:
                    logger.warning("Task %s: failed to parse structured output: %s", task.id, e)
                    await _schedule_retry(task, output=full_output, runner_logs=stderr)
                    continue

                # completed → completed column, needs_input → review column
                target_status = "completed" if parsed.status == "completed" else "review"

                async with async_session() as session:
                    new_position = await _next_position(session, target_status)
                    values = {
                        "status": target_status,
                        "position": new_position,
                        "output": parsed.result,
                        "runner_logs": stderr,
                        "retry_count": 0,
                        "updated_at": datetime.now(timezone.utc),
                    }
                    await session.execute(
                        update(Task).where(Task.id == task.id).values(**values)
                    )

                    # If needs_input, add "Input Needed" tag
                    if parsed.status == "needs_input":
                        result = await session.execute(
                            select(Tag).where(Tag.name == "Input Needed")
                        )
                        tag = result.scalar_one_or_none()
                        if tag is None:
                            tag = Tag(name="Input Needed")
                            session.add(tag)
                            await session.flush()
                        # Add tag to task via association table (guard against duplicates)
                        existing = await session.execute(
                            select(task_tags).where(
                                task_tags.c.task_id == task.id,
                                task_tags.c.tag_id == tag.id,
                            )
                        )
                        if existing.first() is None:
                            await session.execute(
                                task_tags.insert().values(task_id=task.id, tag_id=tag.id)
                            )

                    # Remove "Retry" tag if present (applies to both completed and review)
                    result = await session.execute(
                        select(Tag).where(Tag.name == "Retry")
                    )
                    retry_tag = result.scalar_one_or_none()
                    if retry_tag is not None:
                        await session.execute(
                            task_tags.delete().where(
                                task_tags.c.task_id == task.id,
                                task_tags.c.tag_id == retry_tag.id,
                            )
                        )

                    await session.commit()
                    result = await session.execute(
                        select(Task).options(selectinload(Task.tags)).where(Task.id == task.id)
                    )
                    updated_task = result.scalar_one()
                    await publish_event("task_updated", _task_to_dict(updated_task))
                logger.info(
                    "Task %s moved to %s (runner_status=%s)", task.id, target_status, parsed.status,
                )
                if target_status == "completed":
                    await _reschedule_if_repeating(updated_task)
            else:
                logger.warning("Task %s container exited with code %d", task.id, exit_code)
                await _schedule_retry(task, output=full_output, runner_logs=stderr)

        except (ImageNotFound, APIError) as e:
            logger.error("Docker error for task %s: %s", task.id, e)
            await _schedule_retry(task, output=f"Docker error: {e}")

        except Exception:
            logger.exception("Task %s failed", task.id)
            await _schedule_retry(task)

    _cleanup_active_container()
    await close_valkey()
    await engine.dispose()
    logger.info("Worker shutting down")


if __name__ == "__main__":
    asyncio.run(run())
