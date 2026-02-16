## Context

The `file-based-skill-injection` change (in progress) establishes the Agent Skills standard for skill delivery. Skills are stored in the DB (`skills` + `skill_files` tables), assembled into a tar archive by `build_skills_archive()`, and written to the container at `/workspace/skills/` via `put_archive()`. The worker also injects a skill manifest into the system prompt via `build_skill_manifest()`.

This change adds a second skill source — a git repository — that feeds into the same pipeline. The worker clones/pulls the repo, parses the skill directories, merges them with DB skills, and passes the combined list to the existing archive and manifest functions.

The worker already has access to the user's SSH private key and git SSH host configuration via the settings table, used for injecting SSH credentials into task runner containers.

## Goals / Non-Goals

**Goals:**

- Allow users to specify a git repository containing Agent Skills directories
- Worker clones/refreshes the repo before each task, ensuring the latest skills
- Git-sourced skills merge seamlessly with DB-managed skills in the existing pipeline
- Git failures trigger the existing retry mechanism, escalating to review after max retries
- Each worker process maintains its own independent clone (no shared state)
- Settings UI allows configuring the repo URL, branch, and base path

**Non-Goals:**

- Visibility of git-sourced skills in the Skills UI (deferred to a future change)
- Cherry-picking individual skills from the repo (all skills at the configured path are used)
- Webhook-driven refresh (polling per task is sufficient)
- Multi-repo support (single repo for now)
- Skill versioning or pinning to a specific commit

## Decisions

### D1: Clone location — per-worker temp directory keyed by repo URL

**Decision**: Each worker process clones the repo to a temporary directory derived from a hash of the repo URL: `/tmp/content-manager-skills-<sha256(url)[:12]>/`. On first use, the directory is created and the repo is cloned. On subsequent tasks, `git pull --ff-only` updates it.

**Alternatives considered**:
- *Shared clone on a PV* — introduces locking complexity between workers. Each worker doing its own clone is simpler and the repo is small (skill files are text).
- *Clone inside the container* — would require git in the task runner image and SSH key setup per container. Unnecessary since the worker already has everything it needs.
- *Fresh clone every task (no cache)* — wasteful for large repos. Incremental pull is faster.

**Rationale**: Stateless per-worker. If a worker pod restarts, it re-clones on the first task — the cost is one `git clone` which is acceptable for a skills repo (small).

### D2: SSH key reuse — use existing `ssh_private_key` setting for git operations

**Decision**: The worker writes the SSH key from the `ssh_private_key` setting to a temp file and sets `GIT_SSH_COMMAND="ssh -i <keyfile> -o StrictHostKeyChecking=accept-new"` for git operations. The `git_ssh_hosts` setting is not needed for the worker's own git access — `StrictHostKeyChecking=accept-new` covers it.

**Alternatives considered**:
- *Separate SSH key for worker git access* — confusing UX, the user has to configure two keys for the same host.
- *HTTPS + token auth* — simpler for some providers but doesn't leverage the existing SSH key infrastructure. Could be added as a future option.

**Rationale**: Reuses existing infrastructure. The user has already configured an SSH key for git — the worker just uses the same one.

### D3: Settings storage — new key in existing settings table

**Decision**: Store the git repo config as `Setting(key="skills_git_repo")` with JSON value:
```json
{
  "url": "git@github.com:org/agent-skills.git",
  "branch": "main",
  "path": "skills"
}
```

All fields are optional except `url`. `branch` defaults to the repo's default branch (omit from `git clone`). `path` defaults to `"."` (repo root).

**Alternatives considered**:
- *Separate settings keys per field* — more settings clutter, harder to manage as a unit.
- *New table* — overkill for a single configuration object.

**Rationale**: Consistent with other structured settings (e.g. `mcp_servers`, `git_ssh_hosts`). No migration needed.

### D4: Name conflict resolution — DB skills win

**Decision**: When merging DB skills and git-sourced skills, if both sources have a skill with the same name, the DB skill takes precedence. The git skill is silently dropped (logged at warning level).

**Alternatives considered**:
- *Git wins* — surprising for a user who explicitly edited a skill in the UI.
- *Error/reject* — too disruptive, blocks task execution over a naming collision.
- *Namespace prefix (e.g. `git:code-review`)* — breaks the Agent Skills standard naming convention.

**Rationale**: DB skills represent intentional user edits. Git is a library source — if you've overridden something locally, your override should stick.

### D5: Git failure handling — reuse existing retry mechanism

**Decision**: If `git clone` or `git pull` fails, the worker raises a `GitSkillsError`. The existing task processing error handler catches it and routes through `_schedule_retry()` (exponential backoff: 1, 2, 4, 8, 16 min). After exhausting `max_retries`, the task moves to `review` with the git error message in the output field.

**Alternatives considered**:
- *Separate retry counter for git vs execution failures* — more complexity, marginal benefit. A misconfigured repo will burn through retries quickly and land in review where the user can fix it.
- *Skip git skills and proceed with DB-only* — masks the problem. The user configured a repo for a reason; if it's broken, they should know.

**Rationale**: Simple, leverages existing infrastructure, provides clear user feedback via the review column.

### D6: SKILL.md parsing — YAML frontmatter + markdown body

**Decision**: `parse_skills_from_directory()` scans the configured base path for subdirectories containing a `SKILL.md` file. Each `SKILL.md` is parsed as YAML frontmatter (between `---` delimiters) for `name` and `description`, with the markdown body as `instructions`. Files in `scripts/`, `references/`, `assets/` subdirectories are read as the skill's attached files.

The output is `list[dict]` matching the shape expected by `build_skills_archive()`: `{name, description, instructions, files: [{path, content}]}`.

**Rationale**: This is the Agent Skills standard format — the same format `build_skills_archive()` writes into the container. Parsing it from disk is the natural inverse.

## Risks / Trade-offs

- **[Latency per task]** Each task invocation runs `git pull`, adding 1-3 seconds of latency. → Acceptable for the guarantee of fresh skills. Could add a cache TTL in future if this becomes a concern.
- **[Large repos]** A repo with many large files would slow clone/pull. → Skills repos should be small (text files). Document this expectation. Could add shallow clone (`--depth 1`) as an optimisation.
- **[SSH key must be configured]** Git-sourced skills require the SSH key setting to be configured for private repos. → The UI should surface this dependency. Public repos work without an SSH key (HTTPS clone).
- **[No HTTPS auth support]** Only SSH auth is supported initially. → Can add HTTPS + token as a future enhancement. SSH covers the common case.
- **[Worker disk usage]** Each worker maintains a clone. → Skills repos are small. The temp directory is cleaned up on worker restart.
