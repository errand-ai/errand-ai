"""TaskManager — async task processing integrated into the FastAPI server.

Replaces the standalone worker process. Runs as an asyncio background task
within the FastAPI lifespan, using Postgres advisory locks for leader
election and asyncio.Semaphore for concurrency control.
"""

import asyncio
import dataclasses
import hashlib
import io
import json
import logging
import os
import re
import secrets
import subprocess
import tarfile
import tempfile
import threading
import time
import uuid
from datetime import datetime, timedelta, timezone
from typing import Literal, Optional
from urllib.parse import urlparse

import httpx
from pydantic import BaseModel, ValidationError
from sqlalchemy import create_engine as create_sync_engine, func, select, text as sa_text, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from container_runtime import ContainerRuntime, DockerRuntime, create_runtime
from database import async_session, engine
from events import get_valkey, publish_event, VALKEY_URL
from models import PlatformCredential, Setting, Skill, Tag, Task, TaskProfile, task_tags
from utils import _next_position

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

HEARTBEAT_INTERVAL = 60  # seconds between heartbeat updates
POLL_INTERVAL = int(os.environ.get("POLL_INTERVAL", "5"))
TASK_RUNNER_IMAGE = os.environ.get("TASK_RUNNER_IMAGE", "errand-task-runner:latest")
MAX_OUTPUT_BYTES = int(os.environ.get("MAX_OUTPUT_BYTES", str(1024 * 1024)))  # 1MB default
PLAYWRIGHT_MCP_URL = os.environ.get("PLAYWRIGHT_MCP_URL", "")
GDRIVE_MCP_URL = os.environ.get("GDRIVE_MCP_URL", "")
ONEDRIVE_MCP_URL = os.environ.get("ONEDRIVE_MCP_URL", "")

# Advisory lock ID for leader election (must fit in int4)
LEADER_LOCK_ID = hash("errand_task_manager") & 0x7FFFFFFF
LEADER_LOCK_CONNECT_ARGS = {
    "keepalives": 1,
    "keepalives_idle": 10,
    "keepalives_interval": 10,
    "keepalives_count": 3,
}

DEFAULT_TASK_PROCESSING_MODEL = "claude-sonnet-4-5-20250929"
MAX_GIT_RETRIES = 5

# Sources considered internal to errand (not external MCP clients).
_INTERNAL_CREATED_BY = {"system", "mcp", "email_poller"}


def _is_external_client(created_by: str | None) -> bool:
    """Return True if the task was created by an external MCP client (e.g. paperclip)."""
    if not created_by:
        return False
    if created_by in _INTERNAL_CREATED_BY:
        return False
    # User emails (contain @) are internal (created via the UI)
    if "@" in created_by:
        return False
    # Jira-originated tasks (e.g. "jira:SCRUM-6")
    if created_by.startswith("jira:"):
        return False
    # GitHub-originated tasks (e.g. "github:dispatch", "github:review:123")
    if created_by.startswith("github:"):
        return False
    return True

DEFAULT_HINDSIGHT_BANK_ID = "errand-tasks"


# ---------------------------------------------------------------------------
# Pydantic model for task runner output
# ---------------------------------------------------------------------------


class TaskRunnerOutput(BaseModel):
    status: Literal["completed", "needs_input"]
    result: str
    questions: list[str] = []


# ---------------------------------------------------------------------------
# Snapshot of a dequeued task
# ---------------------------------------------------------------------------


@dataclasses.dataclass
class DequeuedTask:
    """Plain snapshot of the task fields needed by the processing coroutine.

    Captured from the ORM instance while the source DB session is still open,
    then passed to the async worker. This avoids ``DetachedInstanceError`` when
    the spawned coroutine accesses task attributes after the session has been
    closed. See B4 in fix-code-review-bugs.
    """

    id: uuid.UUID
    title: str
    description: str | None
    category: str | None
    profile_id: uuid.UUID | None
    repeat_interval: str | None
    repeat_until: datetime | None
    tag_ids: list[uuid.UUID]
    created_by: str | None = None
    encrypted_env: str | None = None

    @classmethod
    def from_orm(cls, task: Task) -> "DequeuedTask":
        """Build a snapshot from an ORM ``Task`` with ``tags`` eager-loaded."""
        return cls(
            id=task.id,
            title=task.title,
            description=task.description,
            category=task.category,
            profile_id=task.profile_id,
            repeat_interval=task.repeat_interval,
            repeat_until=task.repeat_until,
            tag_ids=[tag.id for tag in task.tags],
            created_by=task.created_by,
            encrypted_env=task.encrypted_env,
        )


# ---------------------------------------------------------------------------
# Helper functions (migrated from worker.py)
# ---------------------------------------------------------------------------


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


def truncate_output(output: str, max_bytes: int = MAX_OUTPUT_BYTES) -> str:
    """Truncate output to max_bytes, appending a marker if exceeded."""
    encoded = output.encode("utf-8")
    if len(encoded) <= max_bytes:
        return output
    truncated = encoded[:max_bytes].decode("utf-8", errors="ignore")
    return truncated + "\n\n--- OUTPUT TRUNCATED (exceeded %d bytes) ---" % max_bytes


_UNIT_WORD_MAP = {
    "minutes": "m", "minute": "m", "mins": "m", "min": "m",
    "hours": "h", "hour": "h", "hrs": "h", "hr": "h",
    "days": "d", "day": "d",
    "weeks": "w", "week": "w",
}
_NAMED_INTERVALS = {"daily": "1d", "weekly": "1w", "hourly": "1h"}


def normalize_interval(interval_str: str) -> str | None:
    """Normalise a human-readable duration string to compact format (e.g. '7 days' → '7d').

    Returns the compact string if normalisation succeeds, or None if unparseable.
    """
    s = interval_str.strip().lower()
    if not s:
        return None

    # Named intervals
    if s in _NAMED_INTERVALS:
        return _NAMED_INTERVALS[s]

    # Already compact (e.g. "7d")
    if re.fullmatch(r"\d+[mhdw]", s):
        return s

    # Human-readable with optional space: "7 days", "30 minutes", "1hour"
    match = re.fullmatch(r"(\d+)\s*([a-z]+)", s)
    if match:
        value, word = match.group(1), match.group(2)
        unit = _UNIT_WORD_MAP.get(word)
        if unit:
            return f"{value}{unit}"

    return None


def parse_interval(interval_str: str) -> timedelta | None:
    """Parse duration strings into timedelta objects.

    Accepts compact format (15m, 1h, 1d, 1w) and human-readable variants
    (7 days, 2 hours, daily, weekly).
    """
    compact = normalize_interval(interval_str)
    if compact is None:
        return None
    match = re.fullmatch(r"(\d+)([mhdw])", compact)
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


class GitSkillsError(Exception):
    """Raised when git clone/pull fails for the skills repository."""
    pass


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
    """Parse Agent Skills directories from a filesystem path."""
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


def build_skills_archive(skills: list[dict]) -> bytes | None:
    """Build a tar archive containing Agent Skills directories."""
    if not skills:
        return None

    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w") as tar:
        for skill in skills:
            name = skill["name"]
            description = skill.get("description", "")
            instructions = skill.get("instructions", "")

            skill_md = f"---\nname: {name}\ndescription: {description}\n---\n\n{instructions}"
            data = skill_md.encode("utf-8")
            info = tarfile.TarInfo(name=f"skills/{name}/SKILL.md")
            info.size = len(data)
            tar.addfile(info, io.BytesIO(data))

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


def recall_from_hindsight(hindsight_url: str, bank_id: str, query: str, max_tokens: int = 2048) -> str | None:
    """Call Hindsight REST API to recall memories relevant to the query."""
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

You have access to cloud storage via MCP servers. Tools are prefixed by provider:
- `gdrive_*` tools operate on Google Drive
- `onedrive_*` tools operate on OneDrive

Available operations: list files, read, write, delete, file info, create folder, move.
Use path-based file access (e.g. `/Documents/report.docx`).

### Concurrency (ETags)
Some operations return an `etag` field. When updating a file, pass the etag you received from the read operation. If the file was modified by another process since you read it, the update will fail with a conflict error — re-read the file and retry.

### Error Handling
- **Permission errors**: The user may not have granted access to the requested file or folder. Report the error clearly.
- **Not found errors**: The file or folder path may be incorrect. Verify the path and try again.
- **Auth errors**: If you receive authentication errors, report that the cloud storage connection may need to be re-established.

### Best Practice
For modifying files: download the file content → modify locally → upload the new version. Avoid attempting in-place edits.
"""


# ---------------------------------------------------------------------------
# Async helpers
# ---------------------------------------------------------------------------


async def _read_settings(session: AsyncSession) -> dict:
    """Read task processing settings from the settings table and skills from the skills table."""
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
        "hot_tools": "",
    }

    result = await session.execute(
        select(Setting).where(
            Setting.key.in_([
                "mcp_servers", "credentials", "task_processing_model",
                "system_prompt", "task_runner_log_level", "mcp_api_key",
                "ssh_private_key", "git_ssh_hosts", "skills_git_repo",
                "hindsight_url", "hindsight_bank_id", "litellm_mcp_servers",
                "hot_tools",
            ])
        )
    )
    for setting in result.scalars().all():
        if setting.key == "mcp_servers":
            settings["mcp_servers"] = setting.value if isinstance(setting.value, dict) else {}
        elif setting.key == "credentials":
            settings["credentials"] = setting.value if isinstance(setting.value, list) else []
        elif setting.key == "task_processing_model":
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
        elif setting.key == "hot_tools":
            settings["hot_tools"] = str(setting.value) if setting.value else ""

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


async def _resolve_profile(session: AsyncSession, task: Task, settings: dict) -> dict:
    """Apply task profile overrides to global settings."""
    if not task.profile_id:
        return settings

    result = await session.execute(select(TaskProfile).where(TaskProfile.id == task.profile_id))
    profile = result.scalar_one_or_none()
    if profile is None:
        logger.warning("Task %s references deleted profile %s, using default settings", task.id, task.profile_id)
        return settings

    resolved = dict(settings)

    if profile.model is not None:
        resolved["task_processing_model"] = profile.model
    if profile.system_prompt is not None:
        resolved["system_prompt"] = profile.system_prompt
    if profile.max_turns is not None:
        resolved["_profile_max_turns"] = str(profile.max_turns)
    if profile.reasoning_effort is not None:
        resolved["_profile_reasoning_effort"] = profile.reasoning_effort

    if profile.mcp_servers is not None:
        resolved["_profile_mcp_servers"] = profile.mcp_servers
    if profile.litellm_mcp_servers is not None:
        resolved["_profile_litellm_mcp_servers"] = profile.litellm_mcp_servers
    if profile.skill_ids is not None:
        resolved["_profile_skill_ids"] = profile.skill_ids

    return resolved


async def _dequeue_task(session: AsyncSession) -> Task | None:
    result = await session.execute(
        select(Task)
        .options(selectinload(Task.tags))
        .where(Task.status == "pending")
        .order_by(Task.position.asc(), Task.created_at.asc())
        .limit(1)
        .with_for_update(skip_locked=True)
    )
    return result.scalar_one_or_none()


# Module-level cache for the sync engine used by ``_resolve_provider_sync``.
# Without this, every lookup built a new SQLAlchemy engine (and its connection
# pool) and never disposed it, exhausting the database connection pool over
# time. See B5 in fix-code-review-bugs.
#
# The lock is needed because ``_resolve_provider_sync`` is invoked via
# ``loop.run_in_executor(None, ...)`` — i.e. concurrently from multiple
# executor threads. A naive ``if is None:`` check would let a burst of
# concurrent callers race into ``create_sync_engine`` and leak pools.
_sync_engine = None
_sync_engine_lock = threading.Lock()


def _get_sync_engine():
    """Return the process-wide sync engine, creating it on first call.

    Thread-safe via double-checked locking: the fast path stays lock-free
    once the engine is initialised.
    """
    global _sync_engine
    if _sync_engine is not None:
        return _sync_engine
    with _sync_engine_lock:
        if _sync_engine is None:
            db_url = os.environ.get("DATABASE_URL", "")
            sync_url = db_url.replace("postgresql+asyncpg://", "postgresql://").replace("sqlite+aiosqlite://", "sqlite://")
            _sync_engine = create_sync_engine(sync_url)
    return _sync_engine


def _resolve_provider_sync(provider_id_str: str) -> dict | None:
    """Resolve provider credentials synchronously for use in executor thread."""
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


def _read_callback_result(task_id: str) -> str | None:
    """Read and delete callback result from Valkey. Returns result string or None."""
    import redis as sync_redis
    try:
        r = sync_redis.Redis.from_url(VALKEY_URL, decode_responses=True)
        result = r.get(f"task_result:{task_id}")
        r.delete(f"task_result:{task_id}", f"task_result_token:{task_id}")
        r.close()
        return result
    except Exception:
        return None


# ---------------------------------------------------------------------------
# TaskManager
# ---------------------------------------------------------------------------


class TaskManager:
    """Async task manager that runs inside the FastAPI server process.

    Uses Postgres advisory locks for leader election and asyncio.Semaphore
    for concurrency control.
    """

    def __init__(self):
        self._running = False
        self._tasks: set[asyncio.Task] = set()
        self._semaphore = asyncio.Semaphore(3)
        self._stop_event = asyncio.Event()
        self._max_concurrent_tasks = 3
        self._runtime: ContainerRuntime | None = None
        self._leader_connection = None
        self._leader_lock_contended = False

    async def run(self):
        """Main loop: acquire leader lock, poll and dispatch tasks."""
        self._running = True
        logger.info("TaskManager starting (poll_interval=%ds)", POLL_INTERVAL)

        # Initialise container runtime
        runtime_type = os.environ.get("CONTAINER_RUNTIME", "docker")
        logger.info("Initialising %s container runtime...", runtime_type)
        try:
            self._runtime = await asyncio.get_event_loop().run_in_executor(None, create_runtime)
        except ValueError as e:
            logger.error("Failed to initialise container runtime: %s", e)
            return

        # Pre-pull images for Docker mode
        if isinstance(self._runtime, DockerRuntime):
            await asyncio.get_event_loop().run_in_executor(None, self._pre_pull_images)

        logger.info("TaskManager started, polling every %ds", POLL_INTERVAL)

        while self._running and not self._stop_event.is_set():
            try:
                has_lock = await self._acquire_leader_lock()
                if not has_lock:
                    if not self._leader_lock_contended:
                        logger.info("Another replica holds the leader lock, waiting...")
                        self._leader_lock_contended = True
                    try:
                        await asyncio.wait_for(self._stop_event.wait(), timeout=POLL_INTERVAL)
                    except TimeoutError:
                        pass
                    continue

                if self._leader_lock_contended:
                    logger.info("Acquired leader lock")
                    self._leader_lock_contended = False
                await self._poll_and_dispatch()

            except Exception:
                logger.exception("TaskManager poll cycle failed")

            if not self._stop_event.is_set():
                try:
                    await asyncio.wait_for(self._stop_event.wait(), timeout=POLL_INTERVAL)
                except TimeoutError:
                    pass

        # Wait for in-flight tasks to complete
        if self._tasks:
            logger.info("Waiting for %d in-flight task(s) to complete...", len(self._tasks))
            done, pending = await asyncio.wait(self._tasks, timeout=300)
            if pending:
                logger.warning("Timed out waiting for %d task(s), cancelling...", len(pending))
                for t in pending:
                    t.cancel()
                await asyncio.wait(pending, timeout=10)

        # Release leader lock connection
        if self._leader_connection is not None:
            try:
                self._leader_connection.close()
            except Exception:
                pass
            self._leader_connection = None

        logger.info("TaskManager stopped")

    async def stop(self):
        """Signal stop and wait for in-flight tasks."""
        logger.info("TaskManager stop requested")
        self._running = False
        self._stop_event.set()

    async def _acquire_leader_lock(self) -> bool:
        """Acquire Postgres advisory lock for leader election.

        Uses a dedicated sync connection (session-scoped lock auto-releases on drop).
        """
        loop = asyncio.get_event_loop()

        def _try_lock():
            if self._leader_connection is None:
                db_url = os.environ.get("DATABASE_URL", "")
                sync_url = db_url.replace("postgresql+asyncpg://", "postgresql://").replace("sqlite+aiosqlite://", "sqlite://")
                # For SQLite (testing), skip advisory locks
                if "sqlite" in sync_url:
                    return True
                eng = create_sync_engine(
                    sync_url,
                    connect_args=LEADER_LOCK_CONNECT_ARGS,
                )
                self._leader_connection = eng.raw_connection()

            try:
                cursor = self._leader_connection.cursor()
                cursor.execute("SELECT pg_try_advisory_lock(%s)", (LEADER_LOCK_ID,))
                result = cursor.fetchone()
                return result[0] if result else False
            except Exception:
                logger.warning("Failed to acquire advisory lock", exc_info=True)
                # Reset connection on error
                try:
                    self._leader_connection.close()
                except Exception:
                    pass
                self._leader_connection = None
                return False

        return await loop.run_in_executor(None, _try_lock)

    async def _poll_and_dispatch(self):
        """Dequeue a pending task and dispatch it for processing."""
        # Read max_concurrent_tasks from settings on each poll cycle
        await self._update_concurrency_setting()

        # Check if semaphore has capacity
        if self._semaphore._value <= 0:  # noqa: SLF001
            return

        async with async_session() as session:
            task = await _dequeue_task(session)
            if task is None:
                return

            # Read settings
            settings = await _read_settings(session)
            settings = await _resolve_profile(session, task, settings)

            # Load GitHub credentials
            github_credentials = None
            try:
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

            # Load Jira credentials for MCP token injection
            jira_credentials = None
            try:
                result = await session.execute(
                    select(PlatformCredential).where(
                        PlatformCredential.platform_id == "jira",
                        PlatformCredential.status == "connected",
                    )
                )
                jira_cred = result.scalar_one_or_none()
                if jira_cred:
                    jira_credentials = decrypt_credentials(jira_cred.encrypted_data)
            except Exception:
                logger.warning("Failed to load Jira credentials", exc_info=True)

            # Load cloud storage credentials
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
            await session.refresh(task, ["tags"])
            await publish_event("task_updated", _task_to_dict(task))

            # Snapshot scalar fields before the session closes so the spawned
            # coroutine never touches a detached ORM instance (B4).
            dequeued = DequeuedTask.from_orm(task)

        # Create asyncio task for processing
        async_task = asyncio.create_task(
            self._run_task(dequeued, settings, github_credentials, cloud_storage_credentials or None, jira_credentials)
        )
        self._tasks.add(async_task)
        async_task.add_done_callback(self._tasks.discard)

    async def _update_concurrency_setting(self):
        """Read max_concurrent_tasks from settings DB and update semaphore if changed."""
        try:
            async with async_session() as session:
                result = await session.execute(
                    select(Setting).where(Setting.key == "max_concurrent_tasks")
                )
                setting = result.scalar_one_or_none()
                if setting is not None:
                    new_max = int(setting.value) if setting.value else 3
                else:
                    # Check env var fallback
                    new_max = int(os.environ.get("MAX_CONCURRENT_TASKS", "3"))

                if new_max != self._max_concurrent_tasks:
                    logger.info("Updating max_concurrent_tasks: %d -> %d", self._max_concurrent_tasks, new_max)
                    self._max_concurrent_tasks = new_max
                    self._semaphore = asyncio.Semaphore(new_max)
        except Exception:
            logger.debug("Failed to read max_concurrent_tasks setting", exc_info=True)

    async def _run_task(
        self,
        task: DequeuedTask,
        settings: dict,
        github_credentials: dict | None = None,
        cloud_storage_credentials: dict | None = None,
        jira_credentials: dict | None = None,
    ):
        """Core task processing coroutine — equivalent to process_task_in_container.

        Receives a plain ``DequeuedTask`` snapshot (not an ORM instance) so that
        field access is safe after the source DB session has closed (B4).
        """
        async with self._semaphore:
            heartbeat_task = None
            try:
                # Start heartbeat periodic task
                heartbeat_task = asyncio.create_task(self._heartbeat_loop(task.id))

                exit_code, stdout, stderr = await self._process_task(
                    task, settings, github_credentials, cloud_storage_credentials,
                    jira_credentials,
                )

                # Combine for display/storage; use stdout only for parsing
                full_output = (stderr + "\n" + stdout).strip() if stderr else stdout

                # Try to extract structured JSON from stdout
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
                        await self._schedule_retry(task, output=full_output, runner_logs=stderr)
                        return

                    if parsed.status == "completed":
                        target_status = "completed"
                    elif parsed.status == "needs_input" and _is_external_client(task.created_by):
                        target_status = "completed"
                        logger.info(
                            "Task %s: needs_input from external client '%s' — completing instead of review",
                            task.id, task.created_by,
                        )
                    else:
                        target_status = "review"

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

                        # Remove "Retry" tag if present
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
                        # Snapshot before session closes so _reschedule_if_repeating
                        # operates on a detached-safe plain dataclass (B4).
                        updated_snapshot = DequeuedTask.from_orm(updated_task)

                    logger.info(
                        "Task %s moved to %s (runner_status=%s)", task.id, target_status, parsed.status,
                    )
                    if target_status == "completed":
                        await self._reschedule_if_repeating(updated_snapshot)
                else:
                    if exit_code != 0:
                        logger.warning("Task %s container exited with code %d", task.id, exit_code)
                    else:
                        logger.warning("Task %s: failed to extract structured output from stdout", task.id)
                    await self._schedule_retry(task, output=full_output, runner_logs=stderr)

            except GitSkillsError as e:
                logger.error("Git skills error for task %s: %s", task.id, e)
                error_str = str(e)
                is_credential_error = any(
                    hint in error_str for hint in ("Permission denied", "publickey", "authentication failed")
                )

                async with async_session() as session:
                    result = await session.execute(select(Task).where(Task.id == task.id))
                    current = result.scalar_one()

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
                        await self._schedule_retry(task, output=error_str)

            except Exception:
                logger.exception("Task %s failed", task.id)
                await self._schedule_retry(task)

            finally:
                if heartbeat_task is not None:
                    heartbeat_task.cancel()
                    try:
                        await heartbeat_task
                    except asyncio.CancelledError:
                        pass

    async def _process_task(
        self,
        task: DequeuedTask,
        settings: dict,
        github_credentials: dict | None = None,
        cloud_storage_credentials: dict | None = None,
        jira_credentials: dict | None = None,
    ) -> tuple[int, str, str]:
        """Run task in a container via the configured runtime. Returns (exit_code, stdout, stderr)."""
        runtime = self._runtime

        mcp_servers = settings.get("mcp_servers", {})
        credentials = settings.get("credentials", [])
        task_processing_model = settings.get("task_processing_model", DEFAULT_TASK_PROCESSING_MODEL)
        system_prompt = settings.get("system_prompt", "")

        # Apply profile mcp_servers filter
        profile_mcp_filter = settings.get("_profile_mcp_servers")
        if profile_mcp_filter is not None:
            if isinstance(mcp_servers, dict) and "mcpServers" in mcp_servers:
                if len(profile_mcp_filter) == 0:
                    mcp_servers = {}
                else:
                    filtered = {k: v for k, v in mcp_servers["mcpServers"].items() if k in profile_mcp_filter}
                    mcp_servers = {"mcpServers": filtered} if filtered else {}

        # Build environment variables from credentials
        env_vars = {}
        for cred in credentials:
            if isinstance(cred, dict) and "key" in cred and "value" in cred:
                env_vars[cred["key"]] = cred["value"]

        # Resolve LLM provider credentials
        openai_base_url = ""
        openai_api_key = ""
        if isinstance(task_processing_model, str):
            task_processing_model = {"provider_id": None, "model": task_processing_model}
        if isinstance(task_processing_model, dict):
            provider_id_str = task_processing_model.get("provider_id")
            model_name = task_processing_model.get("model", "")
            if provider_id_str:
                provider_creds = await asyncio.get_event_loop().run_in_executor(
                    None, _resolve_provider_sync, provider_id_str,
                )
                if provider_creds is None:
                    _err = "LLM provider not configured"
                    logger.error("Task %s: %s", task.id, _err)
                    return (-1, json.dumps({"error": _err}), _err)
                openai_base_url = provider_creds["base_url"]
                openai_api_key = provider_creds["api_key"]
                task_processing_model = model_name
            elif model_name:
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

        # Hot tools for lazy MCP tool loading
        hot_tools = settings.get("hot_tools", "")
        if hot_tools:
            env_vars["HOT_TOOLS"] = hot_tools

        # Internal key for K8s runtime labels
        env_vars["_TASK_ID"] = str(task.id)

        # Inject GitHub token if integration is connected
        if github_credentials:
            try:
                auth_mode = github_credentials.get("auth_mode", "pat")
                if auth_mode == "pat":
                    pat = github_credentials.get("personal_access_token", "")
                    if pat:
                        env_vars["GH_TOKEN"] = pat
                elif auth_mode == "app":
                    from platforms.github import mint_installation_token
                    token = await asyncio.get_event_loop().run_in_executor(
                        None,
                        lambda: mint_installation_token(
                            app_id=github_credentials["app_id"],
                            private_key=github_credentials["private_key"],
                            installation_id=github_credentials["installation_id"],
                        ),
                    )
                    env_vars["GH_TOKEN"] = token
            except Exception:
                logger.warning("Failed to inject GitHub token, skipping GH_TOKEN", exc_info=True)

        # Resolve Hindsight configuration
        hindsight_url = os.environ.get("HINDSIGHT_URL", "") or settings.get("hindsight_url", "")
        hindsight_bank_id = (
            os.environ.get("HINDSIGHT_BANK_ID", "")
            or settings.get("hindsight_bank_id", "")
            or DEFAULT_HINDSIGHT_BANK_ID
        )

        # Pre-load memories from Hindsight
        if hindsight_url:
            recall_query = f"{task.title}. {task.description or ''}"
            recalled = await asyncio.get_event_loop().run_in_executor(
                None, recall_from_hindsight, hindsight_url, hindsight_bank_id, recall_query,
            )
            if recalled:
                system_prompt += (
                    "\n\n## Relevant Context from Memory\n\n"
                    + recalled
                )

        # Inject errand MCP server
        errand_mcp_url = os.environ.get("ERRAND_MCP_URL", "")
        mcp_api_key = settings.get("mcp_api_key", "")
        if errand_mcp_url and mcp_api_key:
            mcp_servers.setdefault("mcpServers", {})
            if "errand" not in mcp_servers["mcpServers"]:
                mcp_servers["mcpServers"]["errand"] = {
                    "url": errand_mcp_url,
                    "headers": {"Authorization": f"Bearer {mcp_api_key}"},
                }

        # Inject Hindsight MCP server
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

        # Inject Playwright MCP server if PLAYWRIGHT_MCP_URL is set
        if PLAYWRIGHT_MCP_URL:
            mcp_servers.setdefault("mcpServers", {})
            if "playwright" not in mcp_servers["mcpServers"]:
                mcp_servers["mcpServers"]["playwright"] = {"url": PLAYWRIGHT_MCP_URL}

        # Inject LiteLLM MCP gateway
        profile_litellm = settings.get("_profile_litellm_mcp_servers")
        if profile_litellm is not None:
            litellm_enabled = profile_litellm
        else:
            litellm_enabled = settings.get("litellm_mcp_servers", [])
        if litellm_enabled and openai_base_url:
            mcp_servers.setdefault("mcpServers", {})
            if "litellm" not in mcp_servers["mcpServers"]:
                base = openai_base_url.rstrip("/")
                litellm_headers = {}
                if openai_api_key:
                    litellm_headers["Authorization"] = f"Bearer {openai_api_key}"
                for server_name in litellm_enabled:
                    key = f"litellm_{server_name}"
                    if key not in mcp_servers["mcpServers"]:
                        mcp_servers["mcpServers"][key] = {
                            "url": f"{base}/mcp/{server_name}",
                            "headers": litellm_headers,
                        }

        # Inject cloud storage MCP servers
        cloud_storage_injected = False
        if cloud_storage_credentials:
            for provider, url_var, mcp_name in [
                ("google_drive", GDRIVE_MCP_URL, "google_drive"),
                ("onedrive", ONEDRIVE_MCP_URL, "onedrive"),
            ]:
                if url_var and provider in cloud_storage_credentials:
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

        # Merge DB skills with git-sourced skills
        skills = settings.get("skills", [])
        skills_git_repo = settings.get("skills_git_repo")
        if skills_git_repo:
            clone_dir = await asyncio.get_event_loop().run_in_executor(
                None,
                refresh_git_clone,
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
                skills = [s for s in skills if s.get("id") and s["id"] in profile_skill_ids]

        # Inject skill manifest
        if skills:
            system_prompt += build_skill_manifest(skills)

        # Inject repo context discovery instructions
        system_prompt += REPO_CONTEXT_INSTRUCTIONS

        # Build environ dict for MCP config variable substitution
        mcp_environ = dict(os.environ)
        if jira_credentials:
            jira_token = jira_credentials.get("api_token", "")
            if jira_token:
                mcp_environ["JIRA_API_TOKEN"] = jira_token
            else:
                logger.debug("Jira credentials present but no api_token, skipping JIRA_API_TOKEN injection")

        # Build files dict for the container
        prompt_text = task.description or task.title
        files = {
            "prompt.txt": prompt_text,
            "system_prompt.txt": system_prompt,
            "mcp.json": json.dumps(substitute_env_vars(mcp_servers, mcp_environ)),
        }

        # Build skills archive
        skills_tar = build_skills_archive(skills) if skills else None

        # SSH credentials
        ssh_private_key = settings.get("ssh_private_key", "")
        ssh_config = generate_ssh_config(settings.get("git_ssh_hosts", [])) if ssh_private_key else None

        # Generate one-time callback token for result push
        if errand_mcp_url:
            try:
                import redis as sync_redis
                cb_redis = sync_redis.Redis.from_url(VALKEY_URL, decode_responses=True)
                callback_token = secrets.token_hex(32)
                cb_redis.set(f"task_result_token:{task.id}", callback_token, ex=1800)
                cb_redis.close()
                callback_url = errand_mcp_url.removesuffix("/").removesuffix("/mcp") + f"/api/internal/task-result/{task.id}"
                env_vars["RESULT_CALLBACK_URL"] = callback_url
                env_vars["RESULT_CALLBACK_TOKEN"] = callback_token
            except Exception:
                logger.warning("Failed to store callback token in Valkey, skipping callback env vars", exc_info=True)

        # Decrypt and inject per-task env vars (overrides global)
        if task.encrypted_env:
            try:
                from platforms.credentials import decrypt
                per_task_env = decrypt(task.encrypted_env)
                env_vars.update(per_task_env)
            except Exception:
                logger.warning("Task %s: failed to decrypt per-task env vars", task.id, exc_info=True)

        # Prepare container via runtime
        git_ssh_hosts = settings.get("git_ssh_hosts", []) if ssh_private_key else []
        handle = await runtime.async_prepare(
            image=TASK_RUNNER_IMAGE,
            env=env_vars,
            files=files,
            output_dir="/output",
            skills_tar=skills_tar,
            ssh_private_key=ssh_private_key or None,
            ssh_config=ssh_config,
            ssh_hosts=git_ssh_hosts or None,
        )
        logger.info("Prepared container for task %s via %s runtime", task.id, os.environ.get("CONTAINER_RUNTIME", "docker"))

        try:
            # Stream logs asynchronously, publishing to Valkey
            log_channel = f"task_logs:{task.id}"
            valkey = get_valkey()

            last_token_refresh = time.monotonic()
            try:
                async for line in runtime.async_run(handle):
                    if not line:
                        continue
                    # Refresh callback token TTL every 15 minutes
                    if valkey is not None and time.monotonic() - last_token_refresh >= 900:
                        try:
                            await valkey.expire(f"task_result_token:{task.id}", 1800)
                            last_token_refresh = time.monotonic()
                        except Exception:
                            logger.warning("Failed to refresh callback token TTL for task %s", task.id, exc_info=True)
                    if valkey is not None:
                        try:
                            parsed_event = json.loads(line)
                            if isinstance(parsed_event, dict) and "type" in parsed_event and "data" in parsed_event:
                                msg = json.dumps({"event": "task_event", "type": parsed_event["type"], "data": parsed_event["data"]})
                            else:
                                msg = json.dumps({"event": "task_event", "type": "raw", "data": {"line": line}})
                        except (json.JSONDecodeError, ValueError):
                            msg = json.dumps({"event": "task_event", "type": "raw", "data": {"line": line}})
                        try:
                            await valkey.publish(log_channel, msg)
                        except Exception:
                            logger.warning("Failed to publish log line to Valkey", exc_info=True)
            except Exception:
                logger.warning("Error during log streaming for task %s", task.id, exc_info=True)

            # Publish end sentinel
            if valkey is not None:
                try:
                    await valkey.publish(log_channel, json.dumps({"event": "task_log_end"}))
                except Exception:
                    logger.warning("Failed to publish task_log_end to Valkey", exc_info=True)

            # Prefer callback result from Valkey; fall back to runtime stdout
            callback_result = await asyncio.get_event_loop().run_in_executor(
                None, _read_callback_result, str(task.id),
            )
            exit_code, stdout, stderr = await runtime.async_result(handle)
            if callback_result is not None:
                stdout = callback_result

            stdout = truncate_output(stdout)
            stderr = truncate_output(stderr)

            return exit_code, stdout, stderr
        finally:
            await runtime.async_cleanup(handle)

    async def _heartbeat_loop(self, task_id):
        """Periodic heartbeat update for a running task."""
        try:
            while True:
                await asyncio.sleep(HEARTBEAT_INTERVAL)
                try:
                    async with async_session() as session:
                        await session.execute(
                            update(Task).where(Task.id == task_id).values(
                                heartbeat_at=datetime.now(timezone.utc),
                            )
                        )
                        await session.commit()
                except Exception:
                    logger.warning("Failed to update heartbeat for task %s", task_id, exc_info=True)
        except asyncio.CancelledError:
            pass

    async def _schedule_retry(self, task: DequeuedTask, output: str | None = None, runner_logs: str | None = None) -> None:
        """Move a failed task back to scheduled with exponential backoff."""
        async with async_session() as session:
            result = await session.execute(select(Task).where(Task.id == task.id))
            current = result.scalar_one()
            new_retry = current.retry_count + 1
            backoff_minutes = 2 ** (current.retry_count)
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

            # Add "Retry" tag
            result = await session.execute(select(Tag).where(Tag.name == "Retry"))
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

    async def _reschedule_if_repeating(self, task: DequeuedTask) -> None:
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

            for tag_id in task.tag_ids:
                await session.execute(
                    task_tags.insert().values(task_id=new_task.id, tag_id=tag_id)
                )

            await session.commit()

            result = await session.execute(
                select(Task).options(selectinload(Task.tags)).where(Task.id == new_task.id)
            )
            new_task_loaded = result.scalar_one()
            await publish_event("task_created", _task_to_dict(new_task_loaded))
            logger.info("Task %s: rescheduled as new task %s", task.id, new_task.id)

    async def _post_result_callback(self, url: str, token: str, result: dict) -> None:
        """Post task result to a callback URL via async httpx."""
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.post(
                    url,
                    json=result,
                    headers={"Authorization": f"Bearer {token}"},
                    timeout=30,
                )
                resp.raise_for_status()
        except Exception:
            logger.warning("Failed to post result callback to %s", url, exc_info=True)

    def _pre_pull_images(self) -> None:
        """Pre-pull required images so the first task starts without download delays."""
        if not isinstance(self._runtime, DockerRuntime):
            return
        from docker.errors import ImageNotFound

        images = [TASK_RUNNER_IMAGE]
        for image in images:
            try:
                self._runtime.client.images.get(image)
                logger.info("Image %s already available", image)
            except ImageNotFound:
                logger.info("Pre-pulling image %s...", image)
                self._runtime.client.images.pull(image)
                logger.info("Pre-pulled image %s", image)
