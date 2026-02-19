import asyncio
import hashlib
import io
import json
import logging
import re
import os
import signal
import subprocess
import tarfile
import tempfile
import time
from datetime import datetime, timedelta, timezone
from typing import Literal, Optional
from urllib.parse import urlparse

import docker
import httpx
from docker.errors import DockerException, APIError, ImageNotFound, NotFound
from pydantic import BaseModel, ValidationError
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from database import async_session, engine
import redis as sync_redis

from events import init_valkey, close_valkey, publish_event, VALKEY_URL
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
TASK_RUNNER_IMAGE = os.environ.get("TASK_RUNNER_IMAGE", "errand-task-runner:latest")
MAX_OUTPUT_BYTES = int(os.environ.get("MAX_OUTPUT_BYTES", str(1024 * 1024)))  # 1MB default
PLAYWRIGHT_MCP_IMAGE = os.environ.get("PLAYWRIGHT_MCP_IMAGE", "")
PLAYWRIGHT_MEMORY_LIMIT = os.environ.get("PLAYWRIGHT_MEMORY_LIMIT", "512m")
PLAYWRIGHT_PORT = int(os.environ.get("PLAYWRIGHT_PORT", "8931"))
PLAYWRIGHT_STARTUP_TIMEOUT = int(os.environ.get("PLAYWRIGHT_STARTUP_TIMEOUT", "30"))

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


def pre_pull_images() -> None:
    """Pre-pull required images so the first task starts without download delays."""
    images = [TASK_RUNNER_IMAGE]
    if PLAYWRIGHT_MCP_IMAGE:
        images.append(PLAYWRIGHT_MCP_IMAGE)

    for image in images:
        try:
            docker_client.images.get(image)
            logger.info("Image %s already available", image)
        except ImageNotFound:
            logger.info("Pre-pulling image %s...", image)
            docker_client.images.pull(image)
            logger.info("Pre-pulled image %s", image)


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


class GitSkillsError(Exception):
    """Raised when git clone/pull fails for the skills repository."""
    pass


MAX_GIT_RETRIES = 5


def refresh_git_clone(repo_url: str, branch: str | None, ssh_private_key: str | None) -> str:
    """Clone or pull the git skills repository. Returns the clone directory path."""
    url_hash = hashlib.sha256(repo_url.encode()).hexdigest()[:12]
    clone_dir = f"/tmp/errand-skills-{url_hash}"

    env = os.environ.copy()
    if ssh_private_key:
        key_file = tempfile.NamedTemporaryFile(mode="w", suffix=".key", delete=False)
        try:
            key_file.write(ssh_private_key)
            key_file.close()
            os.chmod(key_file.name, 0o600)
            env["GIT_SSH_COMMAND"] = f"ssh -i {key_file.name} -o StrictHostKeyChecking=accept-new"
        except Exception:
            os.unlink(key_file.name)
            raise
    else:
        key_file = None

    try:
        if os.path.isdir(os.path.join(clone_dir, ".git")):
            # Pull updates
            subprocess.run(
                ["git", "pull", "--ff-only"],
                cwd=clone_dir,
                env=env,
                capture_output=True,
                text=True,
                check=True,
            )
            logger.info("Pulled updates for skills repo in %s", clone_dir)
        else:
            # Clone
            cmd = ["git", "clone"]
            if branch:
                cmd.extend(["-b", branch])
            cmd.extend([repo_url, clone_dir])
            subprocess.run(
                cmd,
                env=env,
                capture_output=True,
                text=True,
                check=True,
            )
            logger.info("Cloned skills repo %s to %s", repo_url, clone_dir)
    except subprocess.CalledProcessError as e:
        error_msg = e.stderr.strip() or e.stdout.strip() or str(e)
        raise GitSkillsError(f"Git operation failed: {error_msg}") from e
    except OSError as e:
        raise GitSkillsError(f"Git not available: {e}") from e
    finally:
        if key_file is not None:
            try:
                os.unlink(key_file.name)
            except OSError:
                logger.warning("Failed to delete temporary SSH key file %s", key_file.name, exc_info=True)

    return clone_dir


def parse_skills_from_directory(base_path: str) -> list[dict]:
    """Parse Agent Skills directories from a filesystem path.

    Scans for subdirectories containing SKILL.md, parses YAML frontmatter
    and markdown body, reads files from scripts/, references/, assets/.
    Returns list[dict] matching build_skills_archive() input format.
    """
    skills = []
    if not os.path.isdir(base_path):
        return skills

    for entry in sorted(os.listdir(base_path)):
        skill_dir = os.path.join(base_path, entry)
        if not os.path.isdir(skill_dir):
            continue
        skill_md_path = os.path.join(skill_dir, "SKILL.md")
        if not os.path.isfile(skill_md_path):
            continue

        with open(skill_md_path, "r", encoding="utf-8") as f:
            content = f.read()

        # Parse YAML frontmatter
        name = entry
        description = ""
        instructions = content
        if content.startswith("---"):
            parts = content.split("---", 2)
            if len(parts) >= 3:
                frontmatter = parts[1].strip()
                instructions = parts[2].strip()
                for line in frontmatter.split("\n"):
                    line = line.strip()
                    if line.startswith("name:"):
                        name = line[len("name:"):].strip()
                    elif line.startswith("description:"):
                        description = line[len("description:"):].strip()

        # Read attached files from scripts/, references/, assets/
        files = []
        for subdir in ("scripts", "references", "assets"):
            subdir_path = os.path.join(skill_dir, subdir)
            if not os.path.isdir(subdir_path):
                continue
            for fname in sorted(os.listdir(subdir_path)):
                fpath = os.path.join(subdir_path, fname)
                if not os.path.isfile(fpath):
                    continue
                with open(fpath, "r", encoding="utf-8") as f:
                    files.append({"path": f"{subdir}/{fname}", "content": f.read()})

        skills.append({
            "name": name,
            "description": description,
            "instructions": instructions,
            "files": files,
        })

    return skills


def merge_skills(db_skills: list[dict], git_skills: list[dict]) -> list[dict]:
    """Merge DB-managed and git-sourced skills. DB wins on name conflicts."""
    db_names = {s["name"] for s in db_skills}
    merged = list(db_skills)
    for skill in git_skills:
        if skill["name"] in db_names:
            logger.warning("Skill name conflict: '%s' exists in both DB and git — using DB version", skill["name"])
        else:
            merged.append(skill)
    return merged


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

    Returns a dict with keys: mcp_servers, credentials, task_processing_model, system_prompt, task_runner_log_level, skills, skills_git_repo.
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
        "skills_git_repo": None,
        "hindsight_url": "",
        "hindsight_bank_id": "",
    }

    result = await session.execute(
        select(Setting).where(
            Setting.key.in_(["mcp_servers", "credentials", "task_processing_model", "system_prompt", "task_runner_log_level", "mcp_api_key", "ssh_private_key", "git_ssh_hosts", "skills_git_repo", "hindsight_url", "hindsight_bank_id"])
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
        elif setting.key == "skills_git_repo":
            val = setting.value
            if isinstance(val, dict) and val.get("url"):
                settings["skills_git_repo"] = val
            else:
                settings["skills_git_repo"] = None
        elif setting.key == "hindsight_url":
            settings["hindsight_url"] = str(setting.value) if setting.value else ""
        elif setting.key == "hindsight_bank_id":
            settings["hindsight_bank_id"] = str(setting.value) if setting.value else ""

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
        "questions": task.questions,
        "retry_count": task.retry_count,
        "tags": sorted([t.name for t in task.tags]),
        "created_at": task.created_at.isoformat() if task.created_at else None,
        "updated_at": task.updated_at.isoformat() if task.updated_at else None,
        "created_by": task.created_by,
        "updated_by": task.updated_by,
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


DEFAULT_HINDSIGHT_BANK_ID = "errand-tasks"


def recall_from_hindsight(hindsight_url: str, bank_id: str, query: str, max_tokens: int = 2048) -> str | None:
    """Call Hindsight REST API to recall memories relevant to the query.

    Returns the recalled text, or None on failure.
    """
    url = f"{hindsight_url.rstrip('/')}/v1/default/banks/{bank_id}/memories/recall"
    try:
        resp = httpx.post(url, json={"query": query, "max_tokens": max_tokens}, timeout=30)
        resp.raise_for_status()
        data = resp.json()
        results = data.get("results") or []
        content = "\n".join(r["text"] for r in results if r.get("text"))
        return content if content else None
    except Exception:
        logger.warning("Failed to recall from Hindsight at %s", url, exc_info=True)
        return None


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


def start_playwright_container():
    """Start a Playwright MCP sidecar container in DinD. Returns the container."""
    container = docker_client.containers.create(
        image=PLAYWRIGHT_MCP_IMAGE,
        command=["--port", str(PLAYWRIGHT_PORT), "--host", "0.0.0.0", "--allowed-hosts", "*"],
        network_mode="host",
        mem_limit=PLAYWRIGHT_MEMORY_LIMIT,
        memswap_limit=PLAYWRIGHT_MEMORY_LIMIT,
        detach=True,
    )
    container.start()
    logger.info("Started Playwright MCP container %s", container.short_id)
    return container


def health_check_playwright(port: int = PLAYWRIGHT_PORT, timeout: int = PLAYWRIGHT_STARTUP_TIMEOUT) -> bool:
    """Poll Playwright MCP endpoint until it responds or timeout. Returns True if healthy."""
    # Playwright runs with network_mode="host" in DinD, so reach it via the DinD host
    if DOCKER_HOST:
        dind_host = urlparse(DOCKER_HOST).hostname or "localhost"
    else:
        dind_host = "localhost"
    url = f"http://{dind_host}:{port}/mcp"
    payload = {
        "jsonrpc": "2.0",
        "method": "initialize",
        "id": 1,
        "params": {
            "protocolVersion": "2025-03-26",
            "capabilities": {},
            "clientInfo": {"name": "healthcheck", "version": "1.0"},
        },
    }
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            resp = httpx.post(
                        url, json=payload, timeout=5,
                        headers={"Accept": "application/json, text/event-stream"},
                    )
            if resp.status_code == 200:
                logger.info("Playwright MCP health check passed at %s", url)
                return True
            logger.debug("Playwright MCP health check got status %s at %s", resp.status_code, url)
        except Exception:
            logger.debug("Playwright MCP health check request failed for %s", url, exc_info=True)
        time.sleep(1)
    logger.error("Playwright MCP health check timed out after %ds at %s", timeout, url)
    return False


def cleanup_playwright_container(container) -> None:
    """Stop and remove the Playwright container. Handles already-removed case gracefully."""
    if container is None:
        return
    try:
        container.stop(timeout=5)
    except Exception:
        pass  # may already be stopped
    try:
        container.remove(force=True)
        logger.info("Cleaned up Playwright container %s", container.short_id)
    except NotFound:
        logger.warning("Playwright container %s already removed (possibly OOM-killed)", container.short_id)
    except Exception:
        logger.warning("Failed to remove Playwright container", exc_info=True)


def process_task_in_container(task: Task, settings: dict) -> tuple[int, str, str]:
    """Run task in a Docker container via DinD. Returns (exit_code, stdout, stderr)."""
    global active_container_id

    playwright_container = None
    playwright_healthy = False

    # Start Playwright sidecar if configured
    if PLAYWRIGHT_MCP_IMAGE:
        try:
            playwright_container = start_playwright_container()
            playwright_healthy = health_check_playwright()
            if not playwright_healthy:
                logger.error("Playwright MCP health check failed, proceeding without Playwright")
                cleanup_playwright_container(playwright_container)
                playwright_container = None
        except Exception:
            logger.warning("Failed to start Playwright container", exc_info=True)
            cleanup_playwright_container(playwright_container)
            playwright_container = None

    try:
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
        max_turns = os.environ.get("MAX_TURNS", "")
        if max_turns:
            env_vars["MAX_TURNS"] = max_turns

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
            # Resolve Hindsight configuration: env var → admin setting → disabled
            hindsight_url = os.environ.get("HINDSIGHT_URL", "") or settings.get("hindsight_url", "")
            hindsight_bank_id = (
                os.environ.get("HINDSIGHT_BANK_ID", "")
                or settings.get("hindsight_bank_id", "")
                or DEFAULT_HINDSIGHT_BANK_ID
            )

            # Pre-load memories from Hindsight and inject into system prompt
            if hindsight_url:
                recall_query = f"{task.title}. {task.description or ''}"
                recalled = recall_from_hindsight(hindsight_url, hindsight_bank_id, recall_query)
                if recalled:
                    system_prompt += (
                        "\n\n## Relevant Context from Memory\n\n"
                        + recalled
                    )

            # Inject Perplexity MCP server if enabled via environment
            if os.environ.get("USE_PERPLEXITY") == "true":
                mcp_servers.setdefault("mcpServers", {})
                if "perplexity-ask" not in mcp_servers["mcpServers"]:
                    mcp_servers["mcpServers"]["perplexity-ask"] = {"url": "$PERPLEXITY_URL"}
                system_prompt += (
                    "\n\n## Web Research\n\n"
                    "You have access to the `perplexity-ask` MCP tool for web search. "
                    "Try it first when you need current information online.\n\n"
                    "**If `perplexity-ask` is unavailable or returns an error**, fall back to "
                    "fetching web content directly using the `execute_command` tool. "
                    "Both `curl` and Python's `httpx` library are available:\n\n"
                    "```\n"
                    "# Fetch a web page with curl\n"
                    "execute_command('curl -sL https://example.com')\n"
                    "\n"
                    "# Fetch JSON from an API with curl\n"
                    "execute_command('curl -sL https://api.example.com/data')\n"
                    "\n"
                    "# Use Python httpx for more complex requests\n"
                    "execute_command('python3 -c \"import httpx; r = httpx.get(\\\"https://example.com\\\"); print(r.text[:5000])\"')\n"
                    "```\n\n"
                    "Use this approach to retrieve documentation, API responses, or any "
                    "public web content needed to complete the task."
                )

            # Inject errand MCP server for task tools (post_tweet, new_task, etc.)
            backend_mcp_url = os.environ.get("BACKEND_MCP_URL", "")
            mcp_api_key = settings.get("mcp_api_key", "")
            if backend_mcp_url and mcp_api_key:
                mcp_servers.setdefault("mcpServers", {})
                if "errand" not in mcp_servers["mcpServers"]:
                    mcp_servers["mcpServers"]["errand"] = {
                        "url": backend_mcp_url,
                        "headers": {"Authorization": f"Bearer {mcp_api_key}"},
                    }

            # Inject Hindsight MCP server and memory instructions
            if hindsight_url:
                mcp_servers.setdefault("mcpServers", {})
                if "hindsight" not in mcp_servers["mcpServers"]:
                    mcp_servers["mcpServers"]["hindsight"] = {
                        "url": f"{hindsight_url.rstrip('/')}/mcp/{hindsight_bank_id}/"
                    }
                system_prompt += (
                    "\n\n## Persistent Memory (Hindsight)\n\n"
                    "You have access to Hindsight memory tools via the `hindsight` MCP server:\n"
                    "- **retain**: Store important facts, decisions, patterns, and learnings for future tasks\n"
                    "- **recall**: Search memories for relevant context about a topic\n"
                    "- **reflect**: Synthesize reasoning across stored memories\n\n"
                    "Use `retain` to save key outcomes, decisions, or context at the end of your task. "
                    "Use `recall` or `reflect` if you need additional context beyond what was pre-loaded."
                )

            # Inject Playwright MCP server if sidecar is healthy
            if playwright_healthy:
                mcp_servers.setdefault("mcpServers", {})
                if "playwright" not in mcp_servers["mcpServers"]:
                    mcp_servers["mcpServers"]["playwright"] = {
                        "url": f"http://localhost:{PLAYWRIGHT_PORT}/mcp"
                    }

            # Merge DB skills with git-sourced skills if configured
            skills = settings.get("skills", [])
            skills_git_repo = settings.get("skills_git_repo")
            if skills_git_repo:
                clone_dir = refresh_git_clone(
                    skills_git_repo["url"],
                    skills_git_repo.get("branch"),
                    settings.get("ssh_private_key") or None,
                )
                base_path = os.path.join(clone_dir, skills_git_repo.get("path", ".").lstrip("/"))
                git_skills = parse_skills_from_directory(base_path)
                logger.info("Found %d git-sourced skill(s) in %s", len(git_skills), base_path)
                skills = merge_skills(skills, git_skills)

            # Inject skill manifest into system prompt if skills are defined
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

            # Start container and stream stderr in real-time
            container.start()

            # Create sync Redis client for publishing log lines to Valkey
            log_channel = f"task_logs:{task.id}"
            log_redis: sync_redis.Redis | None = None
            try:
                log_redis = sync_redis.Redis.from_url(VALKEY_URL, decode_responses=True)
            except Exception:
                logger.warning("Failed to create sync Redis client for log streaming", exc_info=True)

            # Stream stderr in real-time, publishing structured events to Valkey.
            # Docker's streaming API sends data in arbitrary byte chunks that may
            # not align with newline boundaries, so we buffer and split on newlines.
            try:
                buf = ""
                for chunk in container.logs(stream=True, follow=True, stderr=True, stdout=False):
                    buf += chunk.decode("utf-8", errors="replace")
                    while "\n" in buf:
                        line, buf = buf.split("\n", 1)
                        if not line:
                            continue
                        if log_redis is not None:
                            try:
                                parsed_event = json.loads(line)
                                if isinstance(parsed_event, dict) and "type" in parsed_event and "data" in parsed_event:
                                    msg = json.dumps({"event": "task_event", "type": parsed_event["type"], "data": parsed_event["data"]})
                                else:
                                    msg = json.dumps({"event": "task_event", "type": "raw", "data": {"line": line}})
                            except (json.JSONDecodeError, ValueError):
                                msg = json.dumps({"event": "task_event", "type": "raw", "data": {"line": line}})
                            try:
                                log_redis.publish(log_channel, msg)
                            except Exception:
                                logger.warning("Failed to publish log line to Valkey", exc_info=True)
                # Flush any remaining buffered content
                if buf.strip() and log_redis is not None:
                    try:
                        parsed_event = json.loads(buf.strip())
                        if isinstance(parsed_event, dict) and "type" in parsed_event and "data" in parsed_event:
                            msg = json.dumps({"event": "task_event", "type": parsed_event["type"], "data": parsed_event["data"]})
                        else:
                            msg = json.dumps({"event": "task_event", "type": "raw", "data": {"line": buf.strip()}})
                    except (json.JSONDecodeError, ValueError):
                        msg = json.dumps({"event": "task_event", "type": "raw", "data": {"line": buf.strip()}})
                    try:
                        log_redis.publish(log_channel, msg)
                    except Exception:
                        logger.warning("Failed to publish log line to Valkey", exc_info=True)
            except Exception:
                logger.warning("Error during stderr streaming for task %s", task.id, exc_info=True)

            # Publish end sentinel
            if log_redis is not None:
                try:
                    log_redis.publish(log_channel, json.dumps({"event": "task_log_end"}))
                except Exception:
                    logger.warning("Failed to publish task_log_end to Valkey", exc_info=True)
                finally:
                    log_redis.close()

            # Container has exited — get exit code and capture full output for parsing
            result = container.wait()
            exit_code = result.get("StatusCode", -1)

            stdout = container.logs(stdout=True, stderr=False).decode("utf-8", errors="replace")
            stderr = container.logs(stdout=False, stderr=True).decode("utf-8", errors="replace")
            stdout = truncate_output(stdout)
            stderr = truncate_output(stderr)

            return exit_code, stdout, stderr
        finally:
            try:
                container.remove(force=True)
            except Exception:
                logger.debug("Failed to remove task-runner container", exc_info=True)
            active_container_id = None
    finally:
        cleanup_playwright_container(playwright_container)


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
            "updated_by": "system",
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
            created_by="system",
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
    await asyncio.get_event_loop().run_in_executor(None, pre_pull_images)

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
            task.updated_by = "system"
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
                        "questions": parsed.questions if parsed.questions else None,
                        "retry_count": 0,
                        "updated_by": "system",
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

        except GitSkillsError as e:
            logger.error("Git skills error for task %s: %s", task.id, e)
            error_str = str(e)
            is_credential_error = any(
                hint in error_str for hint in ("Permission denied", "publickey", "authentication failed")
            )
            # Check if we've exceeded max retries — move to review if so
            async with async_session() as session:
                result = await session.execute(select(Task).where(Task.id == task.id))
                current = result.scalar_one()

                # Add "Credentials" tag if this is an SSH/auth failure
                if is_credential_error:
                    result2 = await session.execute(
                        select(Tag).where(Tag.name == "Credentials")
                    )
                    cred_tag = result2.scalar_one_or_none()
                    if cred_tag is None:
                        cred_tag = Tag(name="Credentials")
                        session.add(cred_tag)
                        await session.flush()
                    existing = await session.execute(
                        select(task_tags).where(
                            task_tags.c.task_id == task.id,
                            task_tags.c.tag_id == cred_tag.id,
                        )
                    )
                    if existing.first() is None:
                        await session.execute(
                            task_tags.insert().values(task_id=task.id, tag_id=cred_tag.id)
                        )

                if current.retry_count >= MAX_GIT_RETRIES:
                    new_position = await _next_position(session, "review")
                    await session.execute(
                        update(Task).where(Task.id == task.id).values(
                            status="review",
                            position=new_position,
                            output=error_str,
                            updated_by="system",
                            updated_at=datetime.now(timezone.utc),
                        )
                    )
                    await session.commit()
                    result = await session.execute(
                        select(Task).options(selectinload(Task.tags)).where(Task.id == task.id)
                    )
                    updated = result.scalar_one()
                    await publish_event("task_updated", _task_to_dict(updated))
                    logger.info("Task %s moved to review after %d git retries", task.id, current.retry_count)
                else:
                    await _schedule_retry(task, output=error_str)

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
