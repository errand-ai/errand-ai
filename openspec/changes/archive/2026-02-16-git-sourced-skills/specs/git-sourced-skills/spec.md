## ADDED Requirements

### Requirement: Git skills repository configuration setting
The system SHALL support a `skills_git_repo` setting stored in the settings table as a JSON object with keys: `url` (required, string — the git clone URL), `branch` (optional, string — defaults to the repository's default branch), and `path` (optional, string — subdirectory within the repo containing skill directories, defaults to `"."`). If the `skills_git_repo` setting does not exist or has an empty/null `url`, git-sourced skills SHALL be disabled.

#### Scenario: Full git repo configuration
- **WHEN** the `skills_git_repo` setting is `{"url": "git@github.com:org/skills.git", "branch": "main", "path": "skills"}`
- **THEN** the worker clones the repository from `git@github.com:org/skills.git`, checks out the `main` branch, and reads skills from the `skills/` subdirectory

#### Scenario: Minimal configuration with only URL
- **WHEN** the `skills_git_repo` setting is `{"url": "git@github.com:org/skills.git"}`
- **THEN** the worker clones the repository using the default branch and reads skills from the repository root

#### Scenario: No git repo configured
- **WHEN** the `skills_git_repo` setting does not exist
- **THEN** the worker skips git skill loading and uses only DB-managed skills

#### Scenario: Empty URL disables git skills
- **WHEN** the `skills_git_repo` setting is `{"url": ""}`
- **THEN** the worker skips git skill loading

### Requirement: Worker clones and refreshes git skills repo before each task
Before assembling skills for a task, the worker SHALL check whether a `skills_git_repo` setting is configured. If so, the worker SHALL ensure a local clone exists in a temporary directory derived from the repo URL (e.g. `/tmp/content-manager-skills-<hash>/`). If no clone exists, the worker SHALL run `git clone`. If a clone already exists, the worker SHALL run `git pull --ff-only` to fetch updates. Each worker process SHALL maintain its own independent clone. The worker SHALL use the SSH private key from the `ssh_private_key` setting for authentication by writing it to a temp file and setting `GIT_SSH_COMMAND="ssh -i <keyfile> -o StrictHostKeyChecking=accept-new"`.

#### Scenario: First task clones the repository
- **WHEN** the worker processes its first task and `skills_git_repo` is configured and no local clone exists
- **THEN** the worker runs `git clone` to create a local copy in the temp directory

#### Scenario: Subsequent task pulls updates
- **WHEN** the worker processes a task and a local clone already exists
- **THEN** the worker runs `git pull --ff-only` to update the clone

#### Scenario: SSH key used for authentication
- **WHEN** the worker clones/pulls a private repository and `ssh_private_key` is configured
- **THEN** the git operation uses the SSH key via `GIT_SSH_COMMAND` environment variable

#### Scenario: Public repo works without SSH key
- **WHEN** the worker clones/pulls a public repository using an HTTPS URL and no `ssh_private_key` is configured
- **THEN** the clone/pull succeeds without SSH configuration

#### Scenario: Branch checkout
- **WHEN** the `skills_git_repo` setting specifies `"branch": "production"`
- **THEN** the worker clones/checks out the `production` branch

### Requirement: Worker parses Agent Skills directories from git clone
After a successful clone/pull, the worker SHALL scan the configured base path for subdirectories containing a `SKILL.md` file. For each such directory, the worker SHALL parse the `SKILL.md` file as YAML frontmatter (between `---` delimiters) for `name` and `description` fields, with the markdown body as `instructions`. The worker SHALL also read any files in `scripts/`, `references/`, and `assets/` subdirectories as attached files. The result SHALL be a list of skill dicts matching the format expected by `build_skills_archive()`: `{name, description, instructions, files: [{path, content}]}`. Directories without a `SKILL.md` file SHALL be silently skipped.

#### Scenario: Parse skill with SKILL.md and files
- **WHEN** the git clone contains `skills/research/SKILL.md` with frontmatter `name: research, description: Web research` and body `Use search tools...`, plus `skills/research/scripts/search.py`
- **THEN** the parsed skill has `name="research"`, `description="Web research"`, `instructions="Use search tools..."`, and `files=[{path: "scripts/search.py", content: ...}]`

#### Scenario: Directory without SKILL.md is skipped
- **WHEN** the git clone contains `skills/.git/` (no SKILL.md)
- **THEN** that directory is not included in the parsed skills list

#### Scenario: Skill with no attached files
- **WHEN** the git clone contains `skills/tweet/SKILL.md` and no `scripts/`, `references/`, or `assets/` subdirectories
- **THEN** the parsed skill has an empty `files` list

### Requirement: Git-sourced and DB skills are merged with DB taking precedence
Before building the skills archive for a task, the worker SHALL merge the DB-managed skills list with the git-sourced skills list. If both sources contain a skill with the same `name`, the DB skill SHALL take precedence and the git skill SHALL be dropped. The worker SHALL log a warning when a name conflict is detected. The merged list SHALL be passed to the existing `build_skills_archive()` and `build_skill_manifest()` functions.

#### Scenario: No conflicts — all skills included
- **WHEN** DB skills are `["code-review"]` and git skills are `["research", "tweet"]`
- **THEN** the merged list contains all three skills

#### Scenario: Name conflict — DB wins
- **WHEN** DB skills include a skill named `"research"` and git skills also include `"research"`
- **THEN** the merged list contains only the DB version of `"research"` and a warning is logged

#### Scenario: No git skills — DB-only
- **WHEN** no `skills_git_repo` is configured
- **THEN** the merged list equals the DB skills list

#### Scenario: No DB skills — git-only
- **WHEN** no skills exist in the DB and git skills are `["research"]`
- **THEN** the merged list contains only the git `"research"` skill

### Requirement: Git clone/pull failure triggers task retry
If the git clone or pull operation fails (network error, authentication error, repository not found), the worker SHALL treat it as a pre-execution error and route the task through the existing `_schedule_retry()` mechanism with exponential backoff. The git error message SHALL be stored in the task's `output` field. After exhausting the maximum retry count, the task SHALL be moved to `review` status for user intervention.

#### Scenario: Transient network error triggers retry
- **WHEN** the worker attempts to pull the git skills repo and the operation fails with a network timeout
- **THEN** the task is moved to `scheduled` status with exponential backoff and a "Retry" tag, and the error message is stored in `output`

#### Scenario: Authentication error triggers retry
- **WHEN** the worker attempts to clone the git skills repo and authentication fails
- **THEN** the task is moved to `scheduled` status for retry with the auth error in `output`

#### Scenario: Max retries exceeded moves to review
- **WHEN** the git clone/pull has failed and the task's `retry_count` has reached the maximum
- **THEN** the task is moved to `review` status with the git error message in `output`

#### Scenario: Git failure does not affect task execution without git repo configured
- **WHEN** no `skills_git_repo` setting is configured
- **THEN** the worker proceeds with DB-only skills without any git operations
