import asyncio
import io
import json
import logging
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
from models import Setting, Tag, Task, task_tags


class TaskRunnerOutput(BaseModel):
    status: Literal["completed", "needs_input"]
    result: str
    questions: list[str] = []

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


def truncate_output(output: str, max_bytes: int = MAX_OUTPUT_BYTES) -> str:
    """Truncate output to max_bytes, appending a marker if exceeded."""
    encoded = output.encode("utf-8")
    if len(encoded) <= max_bytes:
        return output
    truncated = encoded[:max_bytes].decode("utf-8", errors="ignore")
    return truncated + "\n\n--- OUTPUT TRUNCATED (exceeded %d bytes) ---" % max_bytes


DEFAULT_TASK_PROCESSING_MODEL = "claude-sonnet-4-5-20250929"


async def read_settings(session: AsyncSession) -> dict:
    """Read task processing settings from the settings table.

    Returns a dict with keys: mcp_servers, credentials, task_processing_model, system_prompt.
    """
    settings: dict = {
        "mcp_servers": {},
        "credentials": [],
        "task_processing_model": DEFAULT_TASK_PROCESSING_MODEL,
        "system_prompt": "",
    }

    result = await session.execute(
        select(Setting).where(
            Setting.key.in_(["mcp_servers", "credentials", "task_processing_model", "system_prompt"])
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
        detach=True,
    )
    active_container_id = container.id
    logger.info("Created container %s for task %s", container.short_id, task.id)

    try:
        # Copy files into the stopped container
        prompt_text = task.description or task.title
        files = {
            "prompt.txt": prompt_text,
            "system_prompt.txt": system_prompt,
            "mcp.json": json.dumps(mcp_servers),
        }
        put_archive(container, files)

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


async def _schedule_retry(task: Task, output: str | None = None) -> None:
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

        await session.execute(
            update(Task).where(Task.id == task.id).values(**values)
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
                # Parse structured output from task runner (stdout only)
                try:
                    parsed = TaskRunnerOutput.model_validate_json(stdout)
                except (ValidationError, ValueError) as e:
                    logger.warning("Task %s: failed to parse structured output: %s", task.id, e)
                    await _schedule_retry(task, output=full_output)
                    continue

                async with async_session() as session:
                    new_position = await _next_position(session, "review")
                    values = {
                        "status": "review",
                        "position": new_position,
                        "output": parsed.result,
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
                        # Add tag to task via association table
                        await session.execute(
                            task_tags.insert().values(task_id=task.id, tag_id=tag.id)
                        )

                    await session.commit()
                    result = await session.execute(
                        select(Task).options(selectinload(Task.tags)).where(Task.id == task.id)
                    )
                    updated_task = result.scalar_one()
                    await publish_event("task_updated", _task_to_dict(updated_task))
                logger.info(
                    "Task %s moved to review (status=%s)", task.id, parsed.status,
                )
            else:
                logger.warning("Task %s container exited with code %d", task.id, exit_code)
                await _schedule_retry(task, output=full_output)

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
