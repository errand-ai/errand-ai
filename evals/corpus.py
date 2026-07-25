"""Corpus loading, validation, and versioning.

A corpus task is one YAML file at ``evals/corpus/<workload>/<nnn>-<slug>.yaml``.
The corpus version recorded with a run is the repo's short git SHA at driver
start; a dirty ``evals/corpus/`` tree makes that SHA unreliable and is warned on.
"""

from __future__ import annotations

import os
import subprocess
from dataclasses import dataclass

import yaml

_REQUIRED_FIELDS = ("id", "base_profile", "description", "rubric", "assertions", "reps", "timeout_minutes")
_ASSERTION_TYPES = ("output_contains", "output_regex", "tool_called")


class CorpusError(Exception):
    """A corpus file is missing a required field or is otherwise invalid."""


@dataclass(frozen=True)
class CorpusTask:
    id: str
    workload: str
    base_profile: str
    description: str
    rubric: str
    assertions: list[dict]
    reps: int
    timeout_minutes: int
    path: str


def _validate(raw: dict, path: str) -> None:
    for field in _REQUIRED_FIELDS:
        if field not in raw or raw[field] is None:
            raise CorpusError(f"{path}: missing required field '{field}'")
    if not isinstance(raw["reps"], int) or raw["reps"] < 1:
        raise CorpusError(f"{path}: 'reps' must be an integer >= 1")
    if not isinstance(raw["timeout_minutes"], int) or raw["timeout_minutes"] < 1:
        raise CorpusError(f"{path}: 'timeout_minutes' must be a positive integer")
    if not isinstance(raw["assertions"], list):
        raise CorpusError(f"{path}: 'assertions' must be a list (may be empty)")
    # Each assertion is a single-key mapping {<type>: <argument>}, e.g.
    # `- tool_called: read_rss_feed` or `- output_regex: "\\d+ jobs found"`.
    for i, a in enumerate(raw["assertions"]):
        if not isinstance(a, dict) or len(a) != 1:
            raise CorpusError(f"{path}: assertion {i} must be a single-key mapping like '{{output_contains: ...}}'")
        atype = next(iter(a))
        if atype not in _ASSERTION_TYPES:
            raise CorpusError(f"{path}: assertion {i} has unknown type '{atype}' (allowed: {list(_ASSERTION_TYPES)})")


def load_task(path: str) -> CorpusTask:
    """Load and validate a single corpus YAML file."""
    try:
        with open(path) as f:
            raw = yaml.safe_load(f)
    except (OSError, yaml.YAMLError) as exc:
        raise CorpusError(f"{path}: cannot read/parse ({exc})") from exc
    if not isinstance(raw, dict):
        raise CorpusError(f"{path}: top-level YAML must be a mapping")
    _validate(raw, path)
    # workload = the directory name under corpus/ (also the prefix of id).
    workload = os.path.basename(os.path.dirname(path))
    return CorpusTask(
        id=str(raw["id"]),
        workload=workload,
        base_profile=str(raw["base_profile"]),
        description=str(raw["description"]),
        rubric=str(raw["rubric"]),
        assertions=list(raw["assertions"]),
        reps=int(raw["reps"]),
        timeout_minutes=int(raw["timeout_minutes"]),
        path=path,
    )


def load_corpus(corpus_dir: str, workload: str | None = None) -> list[CorpusTask]:
    """Load every corpus task (optionally filtered to one workload), sorted by id.

    Raises CorpusError on the first invalid file, naming file and field, before
    the caller submits anything.
    """
    tasks: list[CorpusTask] = []
    roots = [os.path.join(corpus_dir, workload)] if workload else [
        os.path.join(corpus_dir, d) for d in sorted(os.listdir(corpus_dir))
        if os.path.isdir(os.path.join(corpus_dir, d))
    ]
    for root in roots:
        if not os.path.isdir(root):
            continue
        for name in sorted(os.listdir(root)):
            if name.endswith((".yaml", ".yml")):
                tasks.append(load_task(os.path.join(root, name)))
    return sorted(tasks, key=lambda t: t.id)


def corpus_version(repo_dir: str) -> tuple[str, bool]:
    """Return (short_git_sha, corpus_is_dirty) for the repo at ``repo_dir``.

    ``corpus_is_dirty`` is True when there are uncommitted changes under
    ``evals/corpus/`` — the recorded SHA then does not describe the actual corpus.
    Returns ("unknown", True) when git is unavailable.
    """
    def _git(*args: str) -> str | None:
        try:
            return subprocess.run(
                ["git", "-C", repo_dir, *args],
                capture_output=True, text=True, check=True,
            ).stdout.strip()
        except (OSError, subprocess.CalledProcessError):
            return None

    sha = _git("rev-parse", "--short", "HEAD")
    if sha is None:
        return "unknown", True
    dirty_out = _git("status", "--porcelain", "--", "evals/corpus")
    dirty = bool(dirty_out)  # non-empty porcelain output => uncommitted changes
    return sha, dirty
