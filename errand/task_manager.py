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

from container_runtime import ContainerRuntime, DockerRuntime, KubernetesRuntime, create_runtime
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
ONEDRIVE_MCP_URL = os.environ.get("ONEDRIVE_MCP_URL", "")
SYSTEM_SKILLS_DIR = os.environ.get("SYSTEM_SKILLS_DIR", "/app/system-skills")

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

# Retry storm guardrails — see openspec/changes/cap-runner-retry-storm.
MAX_RETRY_BACKOFF_MINUTES = 60
DEFAULT_MAX_RETRY_ATTEMPTS = 5

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

# TTL (seconds) for the per-task Google Workspace refresh bearer stored in
# Valkey under `google_refresh_token:<bearer>`. Chosen to outlast any
# reasonable task duration; the runner only needs the bearer while the task
# is in flight. Independent of the OAuth access token's own 60-min TTL.
GOOGLE_REFRESH_TOKEN_TTL_SECONDS = 8 * 60 * 60  # 8 hours


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
        # Include root-level dependency files (requirements.txt, package.json)
        for dep_file in ("requirements.txt", "package.json"):
            dep_path = os.path.join(skill_dir, dep_file)
            if os.path.isfile(dep_path):
                with open(dep_path, "r", encoding="utf-8") as f:
                    files.append({"path": dep_file, "content": f.read()})
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


def merge_skills_with_plugins(
    db_skills: list[dict],
    git_skills: list[dict],
    system_skills: list[dict] | None = None,
    plugin_skills: list[dict] | None = None,
) -> tuple[list[dict], dict[str, list[dict]]]:
    """Merge skills from DB, plugin, git, and system sources.

    Precedence: DB > plugin > git > system. Plugin-vs-plugin name collisions
    are resolved deterministically by alphabetical plugin name (caller passes
    plugin_skills pre-sorted).

    Returns (merged_skills, plugin_conflicts) where plugin_conflicts maps a
    plugin_name to a list of conflict objects:
        [{"skill": "<skill_name>", "other": "<other_source>"}, ...]
    matching the shape the frontend renders.
    """
    seen: dict[str, str] = {s["name"]: "db" for s in db_skills}
    merged = list(db_skills)
    plugin_conflicts: dict[str, list[dict]] = {}
    for skill in plugin_skills or []:
        name = skill["name"]
        plugin_name = skill.get("_plugin_name", "")
        if name in seen:
            origin = seen[name]
            logger.warning(
                "Skill name conflict: '%s' from plugin '%s' overridden by %s source",
                name, plugin_name, origin,
            )
            if plugin_name:
                plugin_conflicts.setdefault(plugin_name, []).append(
                    {"skill": name, "other": origin}
                )
        else:
            merged.append(skill)
            seen[name] = f"plugin:{plugin_name}" if plugin_name else "plugin"
    for skill in git_skills:
        name = skill["name"]
        if name in seen:
            logger.warning(
                "Skill name conflict: '%s' from git overridden by %s source",
                name, seen[name],
            )
        else:
            merged.append(skill)
            seen[name] = "git"
    for skill in system_skills or []:
        name = skill["name"]
        if name in seen:
            logger.info(
                "System skill '%s' overridden by %s source", name, seen[name],
            )
        else:
            merged.append(skill)
            seen[name] = "system"
    return merged, plugin_conflicts


def merge_skills(
    db_skills: list[dict],
    git_skills: list[dict],
    system_skills: list[dict] | None = None,
) -> list[dict]:
    """Backwards-compatible wrapper returning only the merged list.

    Precedence: DB > git > system (no plugin source). For the plugin-aware
    variant, see `merge_skills_with_plugins`.
    """
    merged, _ = merge_skills_with_plugins(db_skills, git_skills, system_skills, None)
    return merged


async def _load_cloud_storage_credentials(session: AsyncSession) -> dict[str, dict]:
    """Load and refresh OAuth credentials for each cloud storage provider.

    For every provider with stored credentials, calls `refresh_token_if_needed`
    so that downstream consumers (env-var injection, MCP authorization headers)
    see a non-expired access_token. Providers with no stored credentials, or
    whose refresh fails, are simply omitted from the returned dict.
    """
    from platforms.credentials import load_credentials
    from cloud_storage import refresh_token_if_needed

    out: dict[str, dict] = {}
    for provider in ("google_drive", "onedrive"):
        try:
            creds = await load_credentials(provider, session)
            if not creds:
                continue
            refreshed = await refresh_token_if_needed(provider, creds, session)
            if refreshed:
                out[provider] = refreshed
            else:
                logger.warning(
                    "Cloud storage token refresh failed for %s, skipping", provider,
                )
        except Exception:
            logger.warning(
                "Failed to load cloud storage credentials for %s", provider, exc_info=True,
            )
    return out


# Cache for parsed system skill sets. Keyed by (skill_set, base_dir) — the
# on-disk content is baked into the image at build time and effectively
# immutable for the process lifetime, so re-parsing on every task is wasted
# work. Cleared by `_reset_system_skills_cache()` in tests.
_SYSTEM_SKILLS_CACHE: dict[tuple[str, str], list[dict]] = {}


def _reset_system_skills_cache() -> None:
    """Test hook — clears the system-skills cache."""
    _SYSTEM_SKILLS_CACHE.clear()


def load_system_skills(skill_set: str, base_dir: str = SYSTEM_SKILLS_DIR) -> list[dict]:
    """Load a system skill set (e.g. 'gws') from `<base_dir>/<skill_set>/`.

    System skills are baked into the errand server image at build time, so the
    parsed result is memoized for the process lifetime. Returns an empty list
    if the directory does not exist (e.g. local dev).
    """
    cache_key = (skill_set, base_dir)
    cached = _SYSTEM_SKILLS_CACHE.get(cache_key)
    if cached is not None:
        return cached

    skill_dir = os.path.join(base_dir, skill_set)
    if not os.path.isdir(skill_dir):
        logger.warning(
            "System skill set '%s' not present at %s — skipping", skill_set, skill_dir,
        )
        _SYSTEM_SKILLS_CACHE[cache_key] = []
        return []
    skills = parse_skills_from_directory(skill_dir)
    logger.info("Loaded %d system skill(s) from %s", len(skills), skill_dir)
    _SYSTEM_SKILLS_CACHE[cache_key] = skills
    return skills


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


# System skill registry — maps runtime conditions to system skill sets baked
# into the server image at /app/system-skills/<path>/. Each entry's condition
# is evaluated against a task context dict at task preparation time. Adding a
# new system skill set requires only: (1) adding the SKILL.md files to the
# image build and (2) adding an entry here.
#
# `exempt_from_profile_filter` (optional, default False) marks a skill set as
# baseline guidance that the profile's external-skill filter SHALL NOT remove.
# These instructions used to be inline in the system prompt (always present);
# moving them to skills must not regress behaviour for profiles that disable
# externally-sourced skills (`include_git_skills=False`). Only `gws` is left
# subject to the filter — that matches its prior behaviour, where the
# Google Workspace prompt block was suppressed when gws skills were filtered.
SYSTEM_SKILL_REGISTRY: list[dict] = [
    {
        "name": "gws",
        "path": "gws",
        "condition": lambda ctx: bool(ctx.get("google_workspace_enabled")),
    },
    {
        "name": "cloud-storage",
        "path": "cloud-storage",
        "condition": lambda ctx: bool(ctx.get("cloud_storage_injected")),
        "exempt_from_profile_filter": True,
    },
    {
        "name": "hindsight",
        "path": "hindsight",
        "condition": lambda ctx: bool(ctx.get("hindsight_url")),
        "exempt_from_profile_filter": True,
    },
    {
        "name": "repo-context",
        "path": "repo-context",
        "condition": lambda ctx: True,
        "exempt_from_profile_filter": True,
    },
    {
        "name": "binary-files",
        "path": "binary-files",
        "condition": lambda ctx: True,
        "exempt_from_profile_filter": True,
    },
    {
        "name": "shared-workspace",
        "path": "shared-workspace",
        "condition": lambda ctx: bool(ctx.get("shared_workspace_enabled")),
        "exempt_from_profile_filter": True,
    },
]


def load_system_skills_from_registry(
    context: dict, base_dir: str = SYSTEM_SKILLS_DIR,
) -> list[dict]:
    """Evaluate the system skill registry against `context` and load matching skill sets.

    Skills loaded from registry entries with `exempt_from_profile_filter=True`
    are tagged with `_exempt_from_profile_filter=True` so the profile's external
    skill filter spares them. The tag is shallow-copied onto each dict to avoid
    mutating the cached parse result.
    """
    out: list[dict] = []
    for entry in SYSTEM_SKILL_REGISTRY:
        try:
            include = entry["condition"](context)
        except Exception:
            logger.warning(
                "System skill registry condition raised for '%s'", entry["name"],
                exc_info=True,
            )
            continue
        if not include:
            continue
        loaded = load_system_skills(entry["path"], base_dir=base_dir)
        if entry.get("exempt_from_profile_filter"):
            loaded = [dict(s, _exempt_from_profile_filter=True) for s in loaded]
        out.extend(loaded)
    return out


# Google Workspace orientation. Kept inline (not a system skill) because the
# block is conditional on whether any gws-* skills survive the per-profile
# skill filter — that filter runs *after* the registry loader, so a registry
# entry would be loaded into the archive even when the prompt block needs to
# be suppressed. Folding this into a skill would require reworking the filter
# / registry interaction; out of scope for the system-prompt-skill-refactor
# change.
GOOGLE_WORKSPACE_INSTRUCTIONS = """

## Google Workspace

You have access to Google Workspace via the `gws` CLI (`/usr/local/bin/gws`).
The OAuth token is pre-injected via the `GOOGLE_WORKSPACE_CLI_TOKEN` env var,
so commands authenticate automatically.

`gws` covers Drive, Gmail, Calendar, Sheets, Docs, Chat, Tasks, and Contacts.
For full reference, agent skills are installed at `/workspace/skills/gws-*/`.
Read the relevant skill's `SKILL.md` (e.g. `gws-drive`, `gws-gmail`) before
issuing commands.

Run `gws --help` or `gws <service> --help` to discover subcommands. Outputs
are JSON by default and can be piped to `jq` for filtering.
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
        "hindsight_token": "",
        "litellm_mcp_servers": [],
        "hot_tools": "",
        "task_processing_timeout": None,
    }

    result = await session.execute(
        select(Setting).where(
            Setting.key.in_([
                "mcp_servers", "credentials", "task_processing_model",
                "system_prompt", "task_runner_log_level", "mcp_api_key",
                "ssh_private_key", "git_ssh_hosts", "skills_git_repo",
                "hindsight_url", "hindsight_bank_id", "hindsight_token", "litellm_mcp_servers",
                "hot_tools", "task_processing_timeout",
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
        elif setting.key == "hindsight_token":
            settings["hindsight_token"] = str(setting.value) if setting.value else ""
        elif setting.key == "litellm_mcp_servers":
            settings["litellm_mcp_servers"] = setting.value if isinstance(setting.value, list) else []
        elif setting.key == "hot_tools":
            settings["hot_tools"] = str(setting.value) if setting.value else ""
        elif setting.key == "task_processing_timeout":
            try:
                parsed_timeout = int(setting.value) if setting.value is not None else None
            except (TypeError, ValueError):
                logger.warning("Ignoring invalid task_processing_timeout setting: %r", setting.value)
                parsed_timeout = None
            if parsed_timeout is not None and parsed_timeout <= 0:
                logger.warning("Ignoring non-positive task_processing_timeout setting: %r", setting.value)
                parsed_timeout = None
            settings["task_processing_timeout"] = parsed_timeout

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
    if profile.llm_timeout is not None:
        resolved["_profile_llm_timeout"] = profile.llm_timeout

    if profile.mcp_servers is not None:
        resolved["_profile_mcp_servers"] = profile.mcp_servers
    if profile.litellm_mcp_servers is not None:
        resolved["_profile_litellm_mcp_servers"] = profile.litellm_mcp_servers
    if profile.skill_ids is not None:
        resolved["_profile_skill_ids"] = profile.skill_ids
        resolved["_profile_include_git_skills"] = profile.include_git_skills
    resolved["_profile_enabled_plugins"] = profile.enabled_plugins or []

    resolved["_profile_shared_workspace_enabled"] = bool(profile.shared_workspace_enabled)
    resolved["_profile_shared_workspace_subpath"] = profile.shared_workspace_subpath

    return resolved


def _resolve_workspace_mounts(settings: dict):
    """Resolve the profile's shared-workspace config into runtime mount specs.

    Returns ``(mounts, requested_but_unconfigured)`` where ``mounts`` is a list
    of `WorkspaceMount` (or None) and the bool flags the specific case where the
    profile enabled the workspace but this deployment has no workspace gateway
    configured — the caller emits a warning transcript event in that case.

    Deployment-level workspace config comes from env vars set by Helm/compose
    (change section 7): ``WORKSPACE_ENABLED`` gates the feature; the source is a
    Kubernetes PVC (``WORKSPACE_PVC_CLAIM``) for the kubernetes runtime, or a
    host path (``WORKSPACE_HOST_PATH``, subpath folded in) / named volume
    (``WORKSPACE_VOLUME``) for the docker and apple runtimes.
    """
    from container_runtime import WorkspaceMount

    if not settings.get("_profile_shared_workspace_enabled"):
        return None, False

    if os.environ.get("WORKSPACE_ENABLED", "").strip().lower() not in ("1", "true", "yes"):
        return None, True

    container_path = os.environ.get("WORKSPACE_CONTAINER_PATH", "/shared")
    subpath = settings.get("_profile_shared_workspace_subpath") or None
    runtime_type = os.environ.get("CONTAINER_RUNTIME", "docker").strip().lower()

    if runtime_type == "kubernetes":
        claim = os.environ.get("WORKSPACE_PVC_CLAIM", "").strip()
        if not claim:
            return None, True
        return [WorkspaceMount(
            container_path=container_path, pvc_claim_name=claim, subpath=subpath,
        )], False

    # Docker (incl. compose gateway) and Apple use a host-path / named-volume source.
    host_base = os.environ.get("WORKSPACE_HOST_PATH", "").strip()
    named_volume = os.environ.get("WORKSPACE_VOLUME", "").strip()
    if host_base:
        host_path = os.path.join(host_base, subpath) if subpath else host_base
        return [WorkspaceMount(container_path=container_path, host_path=host_path)], False
    if named_volume:
        # Named volumes cannot carry a subpath; the volume is expected to already
        # point at the intended workspace (sub)folder.
        return [WorkspaceMount(container_path=container_path, host_path=named_volume)], False
    return None, True


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


def _resolve_init_value(key: str, registry: dict, coerce):
    """Sync env→default resolution for TaskManager.__init__ (DB unavailable).

    Mirrors the env path of `settings_registry.resolve_setting_value` so that
    initial values match the steady-state code path. Falls back to the
    registered default on coercion failure.
    """
    meta = registry[key]
    default = meta["default"]
    env_var = meta["env_var"]
    env_value = os.environ.get(env_var) if env_var else None
    if env_value is not None and env_value != "":
        try:
            return coerce(env_value, default)
        except Exception:
            logger.warning("Failed to coerce env value for %s on init; using default", key)
            return default
    return default


class TaskManager:
    """Async task manager that runs inside the FastAPI server process.

    Uses Postgres advisory locks for leader election and asyncio.Semaphore
    for concurrency control.
    """

    def __init__(self):
        self._running = False
        self._tasks: set[asyncio.Task] = set()
        self._stop_event = asyncio.Event()
        # __init__ is sync and runs before an event loop exists; resolve via env→default
        # only (the DB pass happens later in _update_concurrency_setting). All three
        # tunables are clamped to >=1 to avoid stalling the semaphore / disabling the
        # log buffer if a deployment ships an out-of-range value.
        from settings_registry import SETTINGS_REGISTRY, _coerce
        self._max_concurrent_tasks = max(
            1, _resolve_init_value("max_concurrent_tasks", SETTINGS_REGISTRY, _coerce)
        )
        self._task_log_buffer_max_entries = max(
            1, _resolve_init_value("task_log_buffer_max_entries", SETTINGS_REGISTRY, _coerce)
        )
        self._task_log_buffer_ttl_seconds = max(
            1, _resolve_init_value("task_log_buffer_ttl_seconds", SETTINGS_REGISTRY, _coerce)
        )
        self._semaphore = asyncio.Semaphore(self._max_concurrent_tasks)
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

        # Pre-pull images for Docker mode; clean up orphaned jobs for K8s
        if isinstance(self._runtime, DockerRuntime):
            await asyncio.get_event_loop().run_in_executor(None, self._pre_pull_images)
        elif isinstance(self._runtime, KubernetesRuntime):
            from container_runtime import cleanup_orphaned_jobs
            await cleanup_orphaned_jobs(self._runtime)

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

            # Load cloud storage credentials (refresh expired tokens up-front so
            # the worker injects fresh values into the task container).
            cloud_storage_credentials = await _load_cloud_storage_credentials(session)

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
        """Read tunable settings via the canonical env→DB→default resolver and update state if changed."""
        from settings_registry import resolve_setting_value
        keys = (
            "max_concurrent_tasks",
            "task_log_buffer_max_entries",
            "task_log_buffer_ttl_seconds",
        )
        try:
            async with async_session() as session:
                result = await session.execute(select(Setting).where(Setting.key.in_(keys)))
                db_rows = {s.key: s.value for s in result.scalars().all()}

                resolved_max, max_source = await resolve_setting_value(
                    session, "max_concurrent_tasks", db_rows=db_rows,
                )
                # Clamp to >=1: a 0 or negative value would create a Semaphore that
                # never permits any task to start, deadlocking the manager.
                new_max = max(1, resolved_max)
                if new_max != resolved_max:
                    logger.warning(
                        "max_concurrent_tasks resolved to %r (source=%s); clamped to %d",
                        resolved_max, max_source, new_max,
                    )
                if new_max != self._max_concurrent_tasks:
                    logger.info(
                        "Updating max_concurrent_tasks: %d -> %d (source=%s)",
                        self._max_concurrent_tasks, new_max, max_source,
                    )
                    self._max_concurrent_tasks = new_max
                    self._semaphore = asyncio.Semaphore(new_max)

                buf_max, buf_max_source = await resolve_setting_value(
                    session, "task_log_buffer_max_entries", db_rows=db_rows
                )
                new_buf_max = max(1, buf_max)
                if new_buf_max != self._task_log_buffer_max_entries:
                    logger.info(
                        "Updating task_log_buffer_max_entries: %d -> %d (source=%s)",
                        self._task_log_buffer_max_entries, new_buf_max, buf_max_source,
                    )
                    self._task_log_buffer_max_entries = new_buf_max

                buf_ttl, buf_ttl_source = await resolve_setting_value(
                    session, "task_log_buffer_ttl_seconds", db_rows=db_rows
                )
                new_buf_ttl = max(1, buf_ttl)
                if new_buf_ttl != self._task_log_buffer_ttl_seconds:
                    logger.info(
                        "Updating task_log_buffer_ttl_seconds: %d -> %d (source=%s)",
                        self._task_log_buffer_ttl_seconds, new_buf_ttl, buf_ttl_source,
                    )
                    self._task_log_buffer_ttl_seconds = new_buf_ttl
        except Exception:
            logger.debug("Failed to read tunable settings", exc_info=True)

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

            except asyncio.CancelledError:
                logger.warning("Task %s processing cancelled, scheduling retry", task.id)
                try:
                    await asyncio.shield(
                        self._schedule_retry(task, output="Processing cancelled during shutdown")
                    )
                except (asyncio.CancelledError, Exception):
                    logger.exception("Failed to schedule retry for cancelled task %s", task.id)
                raise

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

        # LLM request timeout: profile override > global setting > built-in default (30s)
        effective_llm_timeout = settings.get("_profile_llm_timeout")
        if effective_llm_timeout is None:
            effective_llm_timeout = settings.get("task_processing_timeout")
        if effective_llm_timeout is None:
            effective_llm_timeout = 30
        env_vars["LLM_REQUEST_TIMEOUT"] = str(effective_llm_timeout)

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
        hindsight_token = os.environ.get("HINDSIGHT_TOKEN", "") or settings.get("hindsight_token", "")

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

        # Inject Hindsight MCP server. The agent reads the `hindsight-memory`
        # system skill (loaded below) for usage instructions; no inline prompt
        # block is appended.
        if hindsight_url:
            mcp_servers.setdefault("mcpServers", {})
            if "hindsight" not in mcp_servers["mcpServers"]:
                hindsight_entry: dict = {
                    "url": f"{hindsight_url.rstrip('/')}/mcp/{hindsight_bank_id}/"
                }
                if hindsight_token:
                    hindsight_entry["headers"] = {
                        "Authorization": f"Bearer {hindsight_token}"
                    }
                mcp_servers["mcpServers"]["hindsight"] = hindsight_entry

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

        # Inject cloud storage MCP servers (OneDrive only — Google Workspace is via gws CLI env var)
        cloud_storage_injected = False
        if cloud_storage_credentials and ONEDRIVE_MCP_URL and "onedrive" in cloud_storage_credentials:
            if profile_mcp_filter is None or "onedrive" in profile_mcp_filter:
                creds = cloud_storage_credentials["onedrive"]
                access_token = creds.get("access_token", "")
                if access_token:
                    mcp_servers.setdefault("mcpServers", {})
                    mcp_servers["mcpServers"]["onedrive"] = {
                        "url": ONEDRIVE_MCP_URL,
                        "headers": {"Authorization": f"Bearer {access_token}"},
                    }
                    cloud_storage_injected = True

        # Cloud storage usage instructions are delivered via the `cloud-storage`
        # system skill (loaded below by the registry) — no inline prompt block.

        # Google Workspace: inject the access token as GOOGLE_WORKSPACE_CLI_TOKEN
        # so the gws CLI in the task-runner image is authenticated. The matching
        # gws agent skills are added to the skills archive below.
        # Note: GOOGLE_WORKSPACE_INSTRUCTIONS is appended later, after the
        # profile skill filter, so the prompt only references skills that
        # actually made it into the archive.
        google_workspace_enabled = False
        if cloud_storage_credentials and "google_drive" in cloud_storage_credentials:
            google_creds = cloud_storage_credentials["google_drive"]
            google_access_token = google_creds.get("access_token", "")
            if google_access_token:
                env_vars["GOOGLE_WORKSPACE_CLI_TOKEN"] = google_access_token
                google_workspace_enabled = True

                # Inject ERRAND_API_URL + a per-task ERRAND_API_KEY so the
                # task-runner can request a mid-task refresh from
                # `POST /api/google/refresh-token` when it detects an
                # UNAUTHENTICATED response from a gws call. Without these the
                # runner-side recovery silently no-ops and any expired-token
                # failure surfaces to the LLM as today.
                #
                # IMPORTANT: ERRAND_API_KEY is a *task-scoped* opaque token,
                # NOT `mcp_api_key`. The MCP key is global and would be
                # readable by any task via `/workspace/mcp.json`; that would
                # let a task that was never granted Google access call this
                # endpoint and read the Google token. The per-task token is
                # stored in Valkey under `google_refresh_token:<token>` →
                # `<task_id>`, with a TTL chosen to outlast any reasonable
                # task duration (`GOOGLE_REFRESH_TOKEN_TTL_SECONDS`).
                errand_base_url = ""
                if errand_mcp_url:
                    errand_base_url = errand_mcp_url.rstrip("/").rsplit("/mcp", 1)[0]
                if errand_base_url:
                    try:
                        import redis as sync_redis
                        gr_redis = sync_redis.Redis.from_url(VALKEY_URL, decode_responses=True)
                        refresh_bearer = secrets.token_hex(32)
                        gr_redis.set(
                            f"google_refresh_token:{refresh_bearer}",
                            str(task.id),
                            ex=GOOGLE_REFRESH_TOKEN_TTL_SECONDS,
                        )
                        gr_redis.close()
                        env_vars["ERRAND_API_URL"] = errand_base_url
                        env_vars["ERRAND_API_KEY"] = refresh_bearer
                    except Exception:
                        logger.warning(
                            "Failed to store Google refresh bearer in Valkey, "
                            "mid-task refresh disabled for task %s",
                            task.id, exc_info=True,
                        )
                else:
                    logger.warning(
                        "Google token injected but mid-task refresh disabled: "
                        "errand_base_url=%r", errand_base_url,
                    )

        # Merge DB skills with git-sourced and system skills (DB > git > system)
        db_skills = settings.get("skills", [])
        git_skills: list[dict] = []
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

        # Load system skills via the registry. Conditions are evaluated against
        # a context dict assembled from current task state.
        system_skill_context = {
            "google_workspace_enabled": google_workspace_enabled,
            "cloud_storage_injected": cloud_storage_injected,
            "hindsight_url": hindsight_url,
            "shared_workspace_enabled": bool(settings.get("_profile_shared_workspace_enabled")),
        }
        system_skills = load_system_skills_from_registry(system_skill_context)

        # Load plugin-sourced skills + MCP servers gated by the profile's
        # enabled_plugins (bundle-level gating). Plugin skills are sorted by
        # plugin_name so plugin-vs-plugin collisions resolve alphabetically.
        plugin_skills: list[dict] = []
        plugin_mcp_servers: dict[str, dict] = {}
        plugin_conflict_map: dict[str, list[str]] = {}
        profile_enabled_plugin_ids = settings.get("_profile_enabled_plugins") or []
        if profile_enabled_plugin_ids:
            try:
                from plugin_marketplace import (
                    parse_plugin_skills as _parse_plugin_skills,
                    namespaced_mcp_servers as _namespaced_mcp_servers,
                    resolve_plugin_scopes as _resolve_plugin_scopes,
                )
                from models import Plugin
                import uuid as _uuid
                plugin_uuids = []
                for pid in profile_enabled_plugin_ids:
                    try:
                        plugin_uuids.append(_uuid.UUID(pid))
                    except (TypeError, ValueError):
                        logger.info("Skipping invalid plugin UUID in enabled_plugins: %r", pid)
                if plugin_uuids:
                    from plugin_marketplace import wait_for_plugin as _wait_for_plugin
                    async with async_session() as _pl_session:
                        # Fetch ALL referenced plugin rows first so we can
                        # distinguish "doesn't exist" from "globally disabled"
                        # and log each case at info level for admin diagnostics
                        # (spec requirement for task-profile-worker-resolution).
                        all_result = await _pl_session.execute(
                            select(Plugin).where(Plugin.id.in_(plugin_uuids))
                        )
                        all_rows = list(all_result.scalars().all())
                        found_ids = {p.id for p in all_rows}
                        missing_ids = [str(pid) for pid in plugin_uuids if pid not in found_ids]
                        for mid in missing_ids:
                            logger.info(
                                "Profile enabled_plugins references missing plugin %s for task %s — skipping",
                                mid, task.id,
                            )
                        disabled = [p for p in all_rows if not p.enabled]
                        for p in disabled:
                            logger.info(
                                "Profile enabled_plugins references globally-disabled plugin %s (%s) for task %s — skipping",
                                p.id, p.plugin_name, task.id,
                            )
                        rows = sorted(
                            [p for p in all_rows if p.enabled], key=lambda p: p.plugin_name,
                        )
                        scopes = await _resolve_plugin_scopes(_pl_session, rows)
                    for ps in scopes:
                        ready = await _wait_for_plugin(ps.plugin.id)
                        if not ready:
                            logger.warning(
                                "Plugin %s not ready for task %s — emitting plugin_unavailable",
                                ps.plugin.plugin_name, task.id,
                            )
                            try:
                                await publish_event(
                                    "plugin_unavailable",
                                    {
                                        "task_id": str(task.id),
                                        "plugin_id": str(ps.plugin.id),
                                        "plugin_name": ps.plugin.plugin_name,
                                    },
                                )
                            except Exception:
                                logger.exception("Failed to publish plugin_unavailable event")
                            continue
                        for s in _parse_plugin_skills(ps.plugin, ps.scope):
                            s["_plugin_name"] = ps.plugin.plugin_name
                            plugin_skills.append(s)
                        for ns_name, cfg in _namespaced_mcp_servers(ps.plugin, ps.scope).items():
                            plugin_mcp_servers[ns_name] = cfg
            except Exception:
                logger.exception("Failed to load plugin skills/MCP — proceeding without")

        skills, plugin_conflict_map = merge_skills_with_plugins(
            db_skills, git_skills, system_skills, plugin_skills,
        )
        settings["_plugin_mcp_servers"] = plugin_mcp_servers
        settings["_plugin_conflicts"] = plugin_conflict_map

        # Merge plugin-sourced MCP servers (already namespaced as `<plugin>__<server>`)
        # into the final mcp_servers dict. Must come after plugin discovery above so
        # plugin_mcp_servers is populated.
        if plugin_mcp_servers:
            mcp_servers.setdefault("mcpServers", {})
            for ns_name, cfg in plugin_mcp_servers.items():
                if ns_name not in mcp_servers["mcpServers"]:
                    mcp_servers["mcpServers"][ns_name] = cfg

        # Persist skill_conflicts back to affected plugin rows so the API surfaces them.
        # Key by plugin ID, not name — `plugin_name` is only unique within a
        # marketplace, so a name-based UPDATE could touch unrelated rows in
        # other marketplaces or manual installs.
        if plugin_conflict_map:
            try:
                from sqlalchemy import update as _sa_update
                name_to_id: dict[str, "uuid.UUID"] = {
                    ps.plugin.plugin_name: ps.plugin.id for ps in scopes
                }
                async with async_session() as _pl_session:
                    for plugin_name, conflicts in plugin_conflict_map.items():
                        pid = name_to_id.get(plugin_name)
                        if pid is None:
                            continue
                        await _pl_session.execute(
                            _sa_update(Plugin)
                            .where(Plugin.id == pid)
                            .values(skill_conflicts=conflicts)
                        )
                    await _pl_session.commit()
            except Exception:
                logger.exception("Failed to persist plugin skill_conflicts")

        # Apply profile skill filter: DB skills filtered by UUID, non-DB (git + system) skills by flag.
        # The `_profile_include_git_skills` flag (sourced from the legacy `include_git_skills`
        # profile column) gates externally-sourced skills like `gws` and git-sourced skills.
        # System skills tagged with `_exempt_from_profile_filter=True` (cloud-storage, hindsight,
        # repo-context, binary-files) are baseline guidance that used to live inline in the
        # system prompt — they survive the filter regardless of `include_external`.
        profile_skill_ids = settings.get("_profile_skill_ids")
        if profile_skill_ids is not None:
            include_external = settings.get("_profile_include_git_skills", True)
            filtered_db = [s for s in skills if s.get("id") and s["id"] in profile_skill_ids]
            non_db = [
                s for s in skills
                if not s.get("id")
                and (include_external or s.get("_exempt_from_profile_filter"))
            ]
            skills = filtered_db + non_db

        # Append Google Workspace prompt instructions only if at least one gws
        # system skill survived filtering. Otherwise the prompt would tell the
        # agent to read /workspace/skills/gws-*/SKILL.md files that aren't in
        # the archive (e.g. when a profile sets include_git_skills=false).
        # The token env var is still injected so the agent can use the binary
        # if it knows about it, but we don't direct it to skills that aren't
        # there.
        if google_workspace_enabled and any(
            s["name"].startswith("gws-") for s in skills
        ):
            system_prompt += GOOGLE_WORKSPACE_INSTRUCTIONS

        # Inject skill manifest
        if skills:
            system_prompt += build_skill_manifest(skills)

        # Repo context discovery and binary-file handling instructions are
        # delivered via the `repo-context` and `binary-files` system skills
        # (loaded above) — no inline prompt blocks for them.

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

        # Resolve shared-workspace mounts from the profile + deployment config.
        workspace_mounts, workspace_unconfigured = _resolve_workspace_mounts(settings)
        if workspace_unconfigured:
            logger.warning(
                "Task %s requested a shared workspace but this deployment has none configured",
                task.id,
            )
            try:
                await publish_event(
                    "workspace_unavailable",
                    {
                        "task_id": str(task.id),
                        "detail": "profile requested a shared workspace but no workspace gateway is configured on this deployment",
                    },
                )
            except Exception:
                logger.exception("Failed to publish workspace_unavailable event")

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
            mounts=workspace_mounts,
        )
        logger.info("Prepared container for task %s via %s runtime", task.id, os.environ.get("CONTAINER_RUNTIME", "docker"))

        try:
            # Stream logs asynchronously, publishing to Valkey
            log_channel = f"task_logs:{task.id}"
            buffer_key = f"task_logs_buffer:{task.id}"
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
                        publish_ok = False
                        try:
                            await valkey.publish(log_channel, msg)
                            publish_ok = True
                        except Exception:
                            logger.warning("Failed to publish log line to Valkey", exc_info=True)
                        # Only mirror to the replay buffer when the live publish
                        # succeeded — keeps the buffer in sync with what
                        # subscribers actually received. Pipelined to avoid 3
                        # round-trips per event.
                        if publish_ok:
                            try:
                                pipe = valkey.pipeline(transaction=False)
                                pipe.rpush(buffer_key, msg)
                                pipe.ltrim(buffer_key, -self._task_log_buffer_max_entries, -1)
                                pipe.expire(buffer_key, self._task_log_buffer_ttl_seconds)
                                await pipe.execute()
                            except Exception:
                                logger.warning("Failed to append log line to Valkey buffer", exc_info=True)
            except Exception:
                logger.warning("Error during log streaming for task %s", task.id, exc_info=True)

            # Publish end sentinel
            if valkey is not None:
                try:
                    await valkey.publish(log_channel, json.dumps({"event": "task_log_end"}))
                except Exception:
                    logger.warning("Failed to publish task_log_end to Valkey", exc_info=True)
                try:
                    await valkey.delete(buffer_key)
                except Exception:
                    logger.warning("Failed to delete Valkey log buffer for task %s", task.id, exc_info=True)

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

    async def _get_max_retry_attempts(self, session: AsyncSession) -> int:
        """Resolve max_retry_attempts via env → DB → default.

        Clamps `<= 0` to `1` so a misconfigured setting still leaves a finite
        retry budget (any failure escalates on the first attempt rather than
        spinning the loop). Non-integer DB values fall back to the default;
        a single WARNING is emitted on that path.
        """
        from settings_registry import resolve_setting_value
        try:
            value, _source = await resolve_setting_value(session, "max_retry_attempts")
        except Exception:
            logger.warning(
                "Failed to resolve max_retry_attempts; using default %d",
                DEFAULT_MAX_RETRY_ATTEMPTS, exc_info=True,
            )
            return DEFAULT_MAX_RETRY_ATTEMPTS
        try:
            ivalue = int(value)
        except (TypeError, ValueError):
            logger.warning(
                "max_retry_attempts resolved to non-integer %r; using default %d",
                value, DEFAULT_MAX_RETRY_ATTEMPTS,
            )
            return DEFAULT_MAX_RETRY_ATTEMPTS
        if ivalue <= 0:
            return 1
        return ivalue

    async def _schedule_retry(self, task: DequeuedTask, output: str | None = None, runner_logs: str | None = None) -> None:
        """Move a failed task back to scheduled with exponential backoff.

        If `current.retry_count >= max_retry_attempts - 1`, escalates the task
        to `review` with a `Failed` tag instead of rescheduling (see
        `_escalate_to_review_failed`). Backoff is capped at
        `MAX_RETRY_BACKOFF_MINUTES` minutes.
        """
        async with async_session() as session:
            result = await session.execute(select(Task).where(Task.id == task.id))
            current = result.scalar_one()

            max_attempts = await self._get_max_retry_attempts(session)
            if current.retry_count >= max_attempts - 1:
                await self._escalate_to_review_failed(
                    session, task, output=output, runner_logs=runner_logs,
                    max_attempts=max_attempts,
                )
                return

            new_retry = current.retry_count + 1
            backoff_minutes = min(2 ** current.retry_count, MAX_RETRY_BACKOFF_MINUTES)
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

    async def _escalate_to_review_failed(
        self,
        session: AsyncSession,
        task: DequeuedTask,
        *,
        output: str | None,
        runner_logs: str | None,
        max_attempts: int,
    ) -> None:
        """Move a task to `review` with a `Failed` tag after exhausting retries.

        Increments `retry_count` one final time, writes a human-readable message
        identifying the cap was reached and quoting the most recent failure
        output, removes any `Retry` tag, adds a `Failed` tag (creating it on
        demand), and publishes a `task_updated` event.
        """
        result = await session.execute(select(Task).where(Task.id == task.id))
        current = result.scalar_one()
        new_retry = current.retry_count + 1

        # Truncate the embedded failure output so a megabyte of upstream stdout
        # doesn't bloat the row (and SSE payload). 4 KiB is enough for a human
        # to triage the failure in the UI; the full output is preserved in
        # `runner_logs` below.
        raw_failure = output if output is not None else "(no output)"
        last_failure = truncate_output(raw_failure, max_bytes=4096)
        message = (
            f"Task exceeded max retries ({max_attempts}) — last failure: "
            f"{last_failure}"
        )

        new_position = await _next_position(session, "review")
        values = {
            "status": "review",
            "position": new_position,
            "output": message,
            "retry_count": new_retry,
            "updated_by": "system",
            "updated_at": datetime.now(timezone.utc),
        }
        if runner_logs is not None:
            values["runner_logs"] = runner_logs
        await session.execute(
            update(Task).where(Task.id == task.id).values(**values)
        )

        # Remove any existing "Retry" tag association.
        retry_result = await session.execute(select(Tag).where(Tag.name == "Retry"))
        retry_tag = retry_result.scalar_one_or_none()
        if retry_tag is not None:
            await session.execute(
                task_tags.delete().where(
                    task_tags.c.task_id == task.id,
                    task_tags.c.tag_id == retry_tag.id,
                )
            )

        # Ensure the "Failed" tag exists and is associated.
        failed_result = await session.execute(select(Tag).where(Tag.name == "Failed"))
        failed_tag = failed_result.scalar_one_or_none()
        if failed_tag is None:
            failed_tag = Tag(name="Failed")
            session.add(failed_tag)
            await session.flush()
        existing = await session.execute(
            select(task_tags).where(
                task_tags.c.task_id == task.id,
                task_tags.c.tag_id == failed_tag.id,
            )
        )
        if existing.first() is None:
            await session.execute(
                task_tags.insert().values(task_id=task.id, tag_id=failed_tag.id)
            )

        await session.commit()
        result = await session.execute(
            select(Task).options(selectinload(Task.tags)).where(Task.id == task.id)
        )
        escalated = result.scalar_one()
        await publish_event("task_updated", _task_to_dict(escalated))
        logger.info(
            "Task %s exceeded max retries (%d), moved to review",
            task.id, new_retry,
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
