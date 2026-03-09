import asyncio
import hashlib
import io
import json
import logging
import re
import os
import secrets
import signal
import subprocess
import tarfile
import tempfile
import time
from datetime import datetime, timedelta, timezone
from typing import Literal, Optional
from urllib.parse import urlparse

import httpx
from pydantic import BaseModel, ValidationError
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from container_runtime import ContainerRuntime, DockerRuntime, create_runtime, RuntimeHandle
from database import async_session, engine
import redis as sync_redis
from sqlalchemy import create_engine as create_sync_engine, text as sa_text

from events import init_valkey, close_valkey, publish_event, VALKEY_URL
from models import Setting, Skill, Tag, Task, TaskProfile, task_tags
from telemetry import TelemetryBuckets, TelemetryReporter

HEARTBEAT_INTERVAL = 60  # seconds between heartbeat updates

# Telemetry: module-level bucket accumulator and reporter
telemetry_buckets = TelemetryBuckets()
telemetry_reporter: TelemetryReporter | None = None

# Lazy sync engine for heartbeat updates from executor thread
_sync_engine = None


def _get_sync_engine():
    """Get or create a sync SQLAlchemy engine for heartbeat updates."""
    global _sync_engine
    if _sync_engine is None:
        db_url = os.environ.get("DATABASE_URL", "")
        # Convert async URL to sync if needed
        sync_url = db_url.replace("postgresql+asyncpg://", "postgresql://").replace("sqlite+aiosqlite://", "sqlite://")
        _sync_engine = create_sync_engine(sync_url)
    return _sync_engine


def _update_heartbeat(task_id) -> None:
    """Update heartbeat_at for a task. Safe to call from executor thread."""
    try:
        eng = _get_sync_engine()
        with eng.connect() as conn:
            conn.execute(
                sa_text("UPDATE tasks SET heartbeat_at = :now WHERE id = :id"),
                {"now": datetime.now(timezone.utc), "id": str(task_id)},
            )
            conn.commit()
    except Exception:
        logger.warning("Failed to update heartbeat for task %s", task_id, exc_info=True)


def _resolve_provider_sync(provider_id_str: str) -> dict | None:
    """Resolve provider credentials synchronously for use in executor thread.

    Returns {"base_url": ..., "api_key": ...} or None if not found.
    """
    try:
        from llm_providers import decrypt_api_key
        eng = _get_sync_engine()
        with eng.connect() as conn:
            row = conn.execute(
                sa_text("SELECT base_url, api_key_encrypted FROM llm_providers WHERE id = :id"),
                {"id": provider_id_str},
            ).fetchone()
            if row is None:
                return None
            return {
                "base_url": row[0],
                "api_key": decrypt_api_key(row[1]),
            }
    except Exception:
        logger.warning("Failed to resolve provider %s", provider_id_str, exc_info=True)
        return None


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
CONTAINER_RUNTIME_TYPE = os.environ.get("CONTAINER_RUNTIME", "docker")
DOCKER_HOST = os.environ.get("DOCKER_HOST", "")
TASK_RUNNER_IMAGE = os.environ.get("TASK_RUNNER_IMAGE", "errand-task-runner:latest")
MAX_OUTPUT_BYTES = int(os.environ.get("MAX_OUTPUT_BYTES", str(1024 * 1024)))  # 1MB default
PLAYWRIGHT_MCP_IMAGE = os.environ.get("PLAYWRIGHT_MCP_IMAGE", "")
PLAYWRIGHT_MEMORY_LIMIT = os.environ.get("PLAYWRIGHT_MEMORY_LIMIT", "512m")
PLAYWRIGHT_PORT = int(os.environ.get("PLAYWRIGHT_PORT", "8931"))
PLAYWRIGHT_STARTUP_TIMEOUT = int(os.environ.get("PLAYWRIGHT_STARTUP_TIMEOUT", "30"))
GDRIVE_MCP_URL = os.environ.get("GDRIVE_MCP_URL", "")
ONEDRIVE_MCP_URL = os.environ.get("ONEDRIVE_MCP_URL", "")

shutdown_requested = False
shutdown_event: Optional[asyncio.Event] = None
container_runtime: ContainerRuntime | None = None
active_handle: RuntimeHandle | None = None

# Keep docker_client for backward compat (Playwright management in Docker mode,
# SIGTERM cleanup, and test imports). Set during runtime init for Docker mode only.
docker_client = None


def handle_sigterm(*_args):
    global shutdown_requested
    logger.info("SIGTERM received, finishing current task before shutdown")
    shutdown_requested = True
    if shutdown_event is not None:
        loop = asyncio.get_event_loop()
        loop.call_soon_threadsafe(shutdown_event.set)
    _cleanup_active_container()


def _cleanup_active_container():
    global active_handle
    if container_runtime is not None and active_handle is not None:
        try:
            container_runtime.cleanup(active_handle)
            logger.info("Cleaned up active container on shutdown")
        except Exception:
            pass
        active_handle = None



def pre_pull_images() -> None:
    """Pre-pull required images so the first task starts without download delays."""
    if docker_client is None:
        return
    from docker.errors import ImageNotFound

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
        "litellm_mcp_servers": [],
    }

    result = await session.execute(
        select(Setting).where(
            Setting.key.in_(["mcp_servers", "credentials", "task_processing_model", "system_prompt", "task_runner_log_level", "mcp_api_key", "ssh_private_key", "git_ssh_hosts", "skills_git_repo", "hindsight_url", "hindsight_bank_id", "litellm_mcp_servers"])
        )
    )
    for setting in result.scalars().all():
        if setting.key == "mcp_servers":
            settings["mcp_servers"] = setting.value if isinstance(setting.value, dict) else {}
        elif setting.key == "credentials":
            settings["credentials"] = setting.value if isinstance(setting.value, list) else []
        elif setting.key == "task_processing_model":
            # Normalize to {provider_id, model} dict; convert legacy strings
            if isinstance(setting.value, dict):
                settings["task_processing_model"] = setting.value
            elif setting.value:
                settings["task_processing_model"] = {"provider_id": None, "model": str(setting.value)}
            else:
                settings["task_processing_model"] = {"provider_id": None, "model": DEFAULT_TASK_PROCESSING_MODEL}
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
        elif setting.key == "litellm_mcp_servers":
            settings["litellm_mcp_servers"] = setting.value if isinstance(setting.value, list) else []

    # Query skills from dedicated tables
    skill_result = await session.execute(
        select(Skill).options(selectinload(Skill.files)).order_by(Skill.name)
    )
    skills_list = []
    for skill in skill_result.scalars().all():
        skills_list.append({
            "id": str(skill.id),
            "name": skill.name,
            "description": skill.description,
            "instructions": skill.instructions,
            "files": [{"path": f.path, "content": f.content} for f in skill.files],
        })
    settings["skills"] = skills_list

    return settings


async def resolve_profile(session: AsyncSession, task: Task, settings: dict) -> dict:
    """Apply task profile overrides to global settings.

    Returns a new settings dict with profile overrides applied.
    If task has no profile or profile was deleted, returns settings unchanged.
    """
    if not task.profile_id:
        return settings

    result = await session.execute(select(TaskProfile).where(TaskProfile.id == task.profile_id))
    profile = result.scalar_one_or_none()
    if profile is None:
        logger.warning("Task %s references deleted profile %s, using default settings", task.id, task.profile_id)
        return settings

    # Copy settings to avoid mutating the original
    resolved = dict(settings)

    # Scalar overrides: non-null value overrides global
    if profile.model is not None:
        resolved["task_processing_model"] = profile.model
    if profile.system_prompt is not None:
        resolved["system_prompt"] = profile.system_prompt
    if profile.max_turns is not None:
        resolved["_profile_max_turns"] = str(profile.max_turns)
    if profile.reasoning_effort is not None:
        resolved["_profile_reasoning_effort"] = profile.reasoning_effort

    # List overrides: null=inherit, []=empty, [items]=subset
    if profile.mcp_servers is not None:
        resolved["_profile_mcp_servers"] = profile.mcp_servers  # [] or ["name", ...]
    if profile.litellm_mcp_servers is not None:
        resolved["_profile_litellm_mcp_servers"] = profile.litellm_mcp_servers
    if profile.skill_ids is not None:
        resolved["_profile_skill_ids"] = profile.skill_ids

    return resolved


async def get_pending_count(session: AsyncSession) -> int:
    """Get the number of tasks with status 'pending'."""
    result = await session.execute(
        select(func.count()).select_from(Task).where(Task.status == "pending")
    )
    return result.scalar() or 0


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



def _task_to_dict(task: Task, profile_name: str | None = None) -> dict:
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
        "heartbeat_at": task.heartbeat_at.isoformat() if task.heartbeat_at else None,
        "profile_id": str(task.profile_id) if task.profile_id else None,
        "profile_name": profile_name,
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

REPO_CONTEXT_INSTRUCTIONS = """

## Repo Context Discovery

After cloning any git repository, you MUST check for the following context files and use them:

### CLAUDE.md (Project Instructions)
After any `git clone`, check if `CLAUDE.md` exists in the repository root. If it does, read the file and treat its contents as project-specific instructions. Follow these instructions when working within that repository — they may contain coding conventions, architecture guidance, tool preferences, or workflow rules.

### Commands (.claude/commands/)
After any `git clone`, check if a `.claude/commands/` directory exists. If it does, list all `.md` files within it recursively. Each `.md` file defines a command:
- The relative path within `.claude/commands/` (without the `.md` extension) forms the command name
- Directory separators become colons (e.g., `.claude/commands/deploy/staging.md` → command `deploy:staging`)
- If the user prompt references a command by name (with or without a leading `/`), read the corresponding `.md` file and execute the steps described in it
- Do not read command files unless the user prompt references them

### Repo-Level Skills (.claude/skills/)
After any `git clone`, check if a `.claude/skills/` directory exists. If it does, find all `SKILL.md` files in subdirectories. For each `SKILL.md`:
- Read only the YAML frontmatter (between `---` delimiters) to get the `name` and `description` fields
- If a skill's description indicates it is relevant to the current task, read the full `SKILL.md` file and follow its instructions
- Do not read the full file for skills that are not relevant to the task
"""


CLOUD_STORAGE_INSTRUCTIONS = """

## Cloud Storage

You have access to cloud storage via MCP servers. Available tools allow you to:
- List, read, create, update, and delete files and folders
- Search for files by name or content
- Use path-based file access (e.g. `/Documents/report.docx`)

### Concurrency (ETags)
Some operations return an `etag` field. When updating a file, pass the etag you received from the read operation. If the file was modified by another process since you read it, the update will fail with a conflict error — re-read the file and retry.

### Error Handling
- **Permission errors**: The user may not have granted access to the requested file or folder. Report the error clearly.
- **Not found errors**: The file or folder path may be incorrect. Verify the path and try again.
- **Auth errors**: If you receive authentication errors, report that the cloud storage connection may need to be re-established.

### Best Practice
For modifying files: download the file content → modify locally → upload the new version. Avoid attempting in-place edits.
"""


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
    # In Docker mode, Playwright runs with network_mode="host" in DinD
    # In K8s mode, Playwright is a sidecar in the same pod, reachable at localhost
    if CONTAINER_RUNTIME_TYPE == "docker" and DOCKER_HOST:
        host = urlparse(DOCKER_HOST).hostname or "localhost"
    else:
        host = "localhost"
    url = f"http://{host}:{port}/mcp"
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
    except Exception:
        logger.warning("Failed to remove Playwright container", exc_info=True)



def _read_callback_result(task_id: str) -> str | None:
    """Read and delete callback result from Valkey. Returns result string or None."""
    try:
        r = sync_redis.Redis.from_url(VALKEY_URL, decode_responses=True)
        result = r.get(f"task_result:{task_id}")
        r.delete(f"task_result:{task_id}", f"task_result_token:{task_id}")
        r.close()
        return result
    except Exception:
        return None


def process_task_in_container(task: Task, settings: dict, github_credentials: dict | None = None, cloud_storage_credentials: dict | None = None) -> tuple[int, str, str]:
    """Run task in a container via the configured runtime. Returns (exit_code, stdout, stderr)."""
    global active_handle

    runtime = container_runtime
    is_docker = CONTAINER_RUNTIME_TYPE == "docker"

    playwright_container = None
    playwright_healthy = False

    # Playwright management differs by runtime:
    # - Docker: start a Playwright container in DinD, health check, cleanup after
    # - K8s: Playwright is a pre-deployed sidecar, just health check it
    if PLAYWRIGHT_MCP_IMAGE:
        if is_docker:
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
        else:
            # K8s mode: Playwright is a sidecar, just health check
            playwright_healthy = health_check_playwright()
            if not playwright_healthy:
                logger.error("Playwright sidecar health check failed, proceeding without Playwright")

    try:
        mcp_servers = settings.get("mcp_servers", {})
        credentials = settings.get("credentials", [])
        task_processing_model = settings.get("task_processing_model", DEFAULT_TASK_PROCESSING_MODEL)
        system_prompt = settings.get("system_prompt", "")

        # Apply profile mcp_servers filter (only affects user-configured servers, not auto-injected)
        profile_mcp_filter = settings.get("_profile_mcp_servers")
        if profile_mcp_filter is not None:
            if isinstance(mcp_servers, dict) and "mcpServers" in mcp_servers:
                if len(profile_mcp_filter) == 0:
                    # Empty list = no user servers
                    mcp_servers = {}
                else:
                    # Keep only servers in the profile's list
                    filtered = {k: v for k, v in mcp_servers["mcpServers"].items() if k in profile_mcp_filter}
                    mcp_servers = {"mcpServers": filtered} if filtered else {}

        # Build environment variables from credentials
        env_vars = {}
        for cred in credentials:
            if isinstance(cred, dict) and "key" in cred and "value" in cred:
                env_vars[cred["key"]] = cred["value"]

        # Resolve LLM provider credentials for the task processing model
        openai_base_url = ""
        openai_api_key = ""
        # Normalize legacy string values to dict format
        if isinstance(task_processing_model, str):
            task_processing_model = {"provider_id": None, "model": task_processing_model}
        if isinstance(task_processing_model, dict):
            provider_id_str = task_processing_model.get("provider_id")
            model_name = task_processing_model.get("model", "")
            if provider_id_str:
                # Explicit provider — resolve its credentials
                provider_creds = _resolve_provider_sync(provider_id_str)
                if provider_creds is None:
                    _err = "LLM provider not configured"
                    logger.error("Task %s: %s", task.id, _err)
                    return (-1, json.dumps({"error": _err}), _err)
                openai_base_url = provider_creds["base_url"]
                openai_api_key = provider_creds["api_key"]
                task_processing_model = model_name
            elif model_name:
                # No provider_id but model specified — use model name directly;
                # OPENAI_BASE_URL/OPENAI_API_KEY may come from env vars or credentials
                task_processing_model = model_name
            else:
                _err = "LLM provider not configured"
                logger.error("Task %s: %s", task.id, _err)
                return (-1, json.dumps({"error": _err}), _err)
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
        # Max turns: profile override > env var
        profile_max_turns = settings.get("_profile_max_turns")
        if profile_max_turns:
            env_vars["MAX_TURNS"] = profile_max_turns
        else:
            max_turns = os.environ.get("MAX_TURNS", "")
            if max_turns:
                env_vars["MAX_TURNS"] = max_turns
        # Reasoning effort from profile
        profile_reasoning = settings.get("_profile_reasoning_effort")
        if profile_reasoning:
            env_vars["REASONING_EFFORT"] = profile_reasoning

        # Internal key for K8s runtime labels (stripped from actual container env)
        env_vars["_TASK_ID"] = str(task.id)

        # Inject GitHub token if integration is connected
        # github_credentials is loaded in the async caller (run_worker) to
        # avoid cross-event-loop issues with asyncio.run() inside run_in_executor.
        if github_credentials:
            try:
                auth_mode = github_credentials.get("auth_mode", "pat")
                if auth_mode == "pat":
                    pat = github_credentials.get("personal_access_token", "")
                    if pat:
                        env_vars["GH_TOKEN"] = pat
                elif auth_mode == "app":
                    from platforms.github import mint_installation_token
                    token = mint_installation_token(
                        app_id=github_credentials["app_id"],
                        private_key=github_credentials["private_key"],
                        installation_id=github_credentials["installation_id"],
                    )
                    env_vars["GH_TOKEN"] = token
            except Exception:
                logger.warning("Failed to inject GitHub token, skipping GH_TOKEN", exc_info=True)

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

        # Inject errand MCP server for task tools (post_tweet, new_task, etc.)
        errand_mcp_url = os.environ.get("ERRAND_MCP_URL", "")
        mcp_api_key = settings.get("mcp_api_key", "")
        if errand_mcp_url and mcp_api_key:
            mcp_servers.setdefault("mcpServers", {})
            if "errand" not in mcp_servers["mcpServers"]:
                mcp_servers["mcpServers"]["errand"] = {
                    "url": errand_mcp_url,
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

        # Inject Playwright MCP server if healthy
        if playwright_healthy:
            mcp_servers.setdefault("mcpServers", {})
            if "playwright" not in mcp_servers["mcpServers"]:
                # Docker: Playwright at localhost (network_mode=host in DinD)
                # K8s: Playwright at pod IP (cross-pod network for task-runner Jobs)
                if is_docker:
                    pw_url = f"http://localhost:{PLAYWRIGHT_PORT}/mcp"
                else:
                    pod_ip = os.environ.get("POD_IP", "localhost")
                    pw_url = f"http://{pod_ip}:{PLAYWRIGHT_PORT}/mcp"
                mcp_servers["mcpServers"]["playwright"] = {"url": pw_url}

        # Inject LiteLLM MCP gateway if enabled servers exist
        # Apply profile litellm_mcp_servers override
        profile_litellm = settings.get("_profile_litellm_mcp_servers")
        if profile_litellm is not None:
            litellm_enabled = profile_litellm
        else:
            litellm_enabled = settings.get("litellm_mcp_servers", [])
        if litellm_enabled and openai_base_url:
            mcp_servers.setdefault("mcpServers", {})
            if "litellm" not in mcp_servers["mcpServers"]:
                litellm_headers = {"x-mcp-servers": ",".join(litellm_enabled)}
                if openai_api_key:
                    litellm_headers["Authorization"] = f"Bearer {openai_api_key}"
                mcp_servers["mcpServers"]["litellm"] = {
                    "url": f"{openai_base_url.rstrip('/')}/mcp",
                    "headers": litellm_headers,
                }

        # Inject cloud storage MCP servers (two-gate: URL set AND credentials exist)
        # Cloud storage participates in profile_mcp_servers filtering
        cloud_storage_injected = False
        if cloud_storage_credentials:
            for provider, url_var, mcp_name in [
                ("google_drive", GDRIVE_MCP_URL, "google_drive"),
                ("onedrive", ONEDRIVE_MCP_URL, "onedrive"),
            ]:
                if url_var and provider in cloud_storage_credentials:
                    # Check profile filter
                    if profile_mcp_filter is not None and mcp_name not in profile_mcp_filter:
                        continue
                    creds = cloud_storage_credentials[provider]
                    access_token = creds.get("access_token", "")
                    if access_token:
                        mcp_servers.setdefault("mcpServers", {})
                        mcp_servers["mcpServers"][mcp_name] = {
                            "url": url_var,
                            "headers": {"Authorization": f"Bearer {access_token}"},
                        }
                        cloud_storage_injected = True

        if cloud_storage_injected:
            system_prompt += CLOUD_STORAGE_INSTRUCTIONS

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

        # Apply profile skill_ids filter
        profile_skill_ids = settings.get("_profile_skill_ids")
        if profile_skill_ids is not None:
            if len(profile_skill_ids) == 0:
                skills = []
            else:
                # Filter DB skills by UUID; git-sourced skills don't have UUIDs so they're excluded
                skills = [s for s in skills if s.get("id") and s["id"] in profile_skill_ids]

        # Inject skill manifest into system prompt if skills are defined
        if skills:
            system_prompt += build_skill_manifest(skills)

        # Inject repo context discovery instructions
        system_prompt += REPO_CONTEXT_INSTRUCTIONS

        # Build files dict for the container
        prompt_text = task.description or task.title
        files = {
            "prompt.txt": prompt_text,
            "system_prompt.txt": system_prompt,
            "mcp.json": json.dumps(substitute_env_vars(mcp_servers)),
        }

        # Build skills archive
        skills_tar = build_skills_archive(skills) if skills else None

        # SSH credentials
        ssh_private_key = settings.get("ssh_private_key", "")
        ssh_config = generate_ssh_config(settings.get("git_ssh_hosts", [])) if ssh_private_key else None

        # Generate one-time callback token for result push
        try:
            cb_redis = sync_redis.Redis.from_url(VALKEY_URL, decode_responses=True)
            callback_token = secrets.token_hex(32)
            cb_redis.set(f"task_result_token:{task.id}", callback_token, ex=1800)
            cb_redis.close()
            callback_url = errand_mcp_url.removesuffix("/").removesuffix("/mcp") + f"/api/internal/task-result/{task.id}"
            env_vars["RESULT_CALLBACK_URL"] = callback_url
            env_vars["RESULT_CALLBACK_TOKEN"] = callback_token
        except Exception:
            logger.warning("Failed to store callback token in Valkey, skipping callback env vars", exc_info=True)

        # Prepare container via runtime
        git_ssh_hosts = settings.get("git_ssh_hosts", []) if ssh_private_key else []
        handle = runtime.prepare(
            image=TASK_RUNNER_IMAGE,
            env=env_vars,
            files=files,
            output_dir="/output",
            skills_tar=skills_tar,
            ssh_private_key=ssh_private_key or None,
            ssh_config=ssh_config,
            ssh_hosts=git_ssh_hosts or None,
        )
        active_handle = handle
        logger.info("Prepared container for task %s via %s runtime", task.id, CONTAINER_RUNTIME_TYPE)

        try:
            # Create sync Redis client for publishing log lines to Valkey
            log_channel = f"task_logs:{task.id}"
            log_redis: sync_redis.Redis | None = None
            try:
                log_redis = sync_redis.Redis.from_url(VALKEY_URL, decode_responses=True)
            except Exception:
                logger.warning("Failed to create sync Redis client for log streaming", exc_info=True)

            # Stream logs in real-time, publishing structured events to Valkey
            last_token_refresh = time.monotonic()
            last_heartbeat = time.monotonic()
            try:
                for line in runtime.run(handle):
                    if not line:
                        continue
                    # Update heartbeat periodically
                    if time.monotonic() - last_heartbeat >= HEARTBEAT_INTERVAL:
                        _update_heartbeat(task.id)
                        last_heartbeat = time.monotonic()
                    # Refresh callback token TTL every 15 minutes
                    if log_redis is not None and time.monotonic() - last_token_refresh >= 900:
                        try:
                            log_redis.expire(f"task_result_token:{task.id}", 1800)
                            last_token_refresh = time.monotonic()
                        except Exception:
                            logger.warning("Failed to refresh callback token TTL for task %s", task.id, exc_info=True)
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
            except Exception:
                logger.warning("Error during log streaming for task %s", task.id, exc_info=True)

            # Publish end sentinel
            if log_redis is not None:
                try:
                    log_redis.publish(log_channel, json.dumps({"event": "task_log_end"}))
                except Exception:
                    logger.warning("Failed to publish task_log_end to Valkey", exc_info=True)
                finally:
                    log_redis.close()

            # Prefer callback result from Valkey; fall back to runtime stdout
            callback_result = _read_callback_result(str(task.id))
            exit_code, stdout, stderr = runtime.result(handle)
            if callback_result is not None:
                stdout = callback_result

            stdout = truncate_output(stdout)
            stderr = truncate_output(stderr)

            return exit_code, stdout, stderr
        finally:
            runtime.cleanup(handle)
            active_handle = None
    finally:
        # In Docker mode, clean up the Playwright container
        if is_docker:
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
            profile_id=task.profile_id,
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
    global shutdown_event, container_runtime, docker_client
    shutdown_event = asyncio.Event()

    signal.signal(signal.SIGTERM, handle_sigterm)
    await init_valkey()

    # Initialise container runtime
    logger.info("Initialising %s container runtime...", CONTAINER_RUNTIME_TYPE)
    try:
        container_runtime = await asyncio.get_event_loop().run_in_executor(None, create_runtime)
    except ValueError as e:
        logger.error("Failed to initialise container runtime: %s", e)
        raise SystemExit(1)

    # For Docker mode, keep docker_client reference for Playwright management and pre-pull
    if isinstance(container_runtime, DockerRuntime):
        docker_client = container_runtime.client
        await asyncio.get_event_loop().run_in_executor(None, pre_pull_images)

    # Start telemetry reporter
    global telemetry_reporter
    telemetry_reporter = TelemetryReporter(telemetry_buckets, async_session)
    await telemetry_reporter.start()

    logger.info("Worker started, polling every %ds", POLL_INTERVAL)

    while not shutdown_requested:
        async with async_session() as session:
            task = await dequeue_task(session)
            if task is not None:
                pending_count = await get_pending_count(session)
                telemetry_buckets.update_max_pending(pending_count)
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

            # Apply task profile overrides
            settings = await resolve_profile(session, task, settings)

            # Load GitHub credentials while we have a session
            github_credentials = None
            try:
                from models import PlatformCredential
                from platforms.credentials import decrypt as decrypt_credentials
                result = await session.execute(
                    select(PlatformCredential).where(
                        PlatformCredential.platform_id == "github",
                        PlatformCredential.status == "connected",
                    )
                )
                gh_cred = result.scalar_one_or_none()
                if gh_cred:
                    github_credentials = decrypt_credentials(gh_cred.encrypted_data)
            except Exception:
                logger.warning("Failed to load GitHub credentials", exc_info=True)

            # Load and refresh cloud storage credentials while we have a session
            cloud_storage_credentials = {}
            for provider in ("google_drive", "onedrive"):
                try:
                    from platforms.credentials import load_credentials
                    creds = await load_credentials(provider, session)
                    if creds:
                        from cloud_storage import refresh_token_if_needed
                        refreshed = await refresh_token_if_needed(provider, creds, session)
                        if refreshed:
                            cloud_storage_credentials[provider] = refreshed
                        else:
                            logger.warning("Cloud storage token refresh failed for %s, skipping", provider)
                except Exception:
                    logger.warning("Failed to load cloud storage credentials for %s", provider, exc_info=True)

            # Set status to running with initial heartbeat
            task.status = "running"
            task.heartbeat_at = datetime.now(timezone.utc)
            task.updated_by = "system"
            await session.commit()
            await session.refresh(task)
            await publish_event("task_updated", _task_to_dict(task))

        # Process outside the dequeue transaction
        try:
            exit_code, stdout, stderr = await asyncio.get_event_loop().run_in_executor(
                None, process_task_in_container, task, settings, github_credentials, cloud_storage_credentials or None
            )
            # Combine for display/storage; use stdout only for parsing
            full_output = (stderr + "\n" + stdout).strip() if stderr else stdout

            # Try to extract structured JSON from stdout regardless of exit code.
            # The task-runner may have completed successfully even if exit code
            # detection failed (e.g. K8s API race returning -1).
            clean_stdout = extract_json(stdout) if stdout else None

            if exit_code != 0 and clean_stdout is not None:
                logger.info(
                    "Task %s: exit_code=%d but found valid structured output, treating as success",
                    task.id, exit_code,
                )

            if clean_stdout is not None:
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
                if exit_code != 0:
                    logger.warning("Task %s container exited with code %d", task.id, exit_code)
                else:
                    logger.warning("Task %s: failed to extract structured output from stdout", task.id)
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

        except Exception:
            logger.exception("Task %s failed", task.id)
            await _schedule_retry(task)

        # Telemetry: record task completion and update pending high-water mark
        telemetry_buckets.increment_completed()
        async with async_session() as session:
            pending_count = await get_pending_count(session)
            telemetry_buckets.update_max_pending(pending_count)

    _cleanup_active_container()
    if telemetry_reporter:
        await telemetry_reporter.stop()
    await close_valkey()
    await engine.dispose()
    logger.info("Worker shutting down")


if __name__ == "__main__":
    asyncio.run(run())
