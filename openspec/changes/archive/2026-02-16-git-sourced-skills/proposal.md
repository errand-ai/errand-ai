## Why

Skills are currently managed exclusively through the Settings UI and stored in the database. Teams and users who already maintain a curated library of Agent Skills in a git repository have no way to use them without manually copying each skill into the UI. By allowing the user to specify a git repository URL, the worker can clone/pull the repo and merge those skills alongside UI-managed skills — enabling version-controlled, collaborative skill management with zero manual sync.

## What Changes

- **New `skills_git_repo` setting**: Users can configure a git repository URL, optional branch, and optional base path (subdirectory within the repo where skills live). Stored as a JSON object in the existing settings table.
- **Worker clones/pulls the git repo before each task**: On every task runner invocation, the worker ensures it has a fresh clone or pulls updates to an existing clone. Each worker process maintains its own independent clone in a temporary directory.
- **Git-sourced skills merged into the skill injection pipeline**: Skills parsed from the git repo are merged with DB-managed skills and fed into the existing `build_skills_archive()` / `build_skill_manifest()` pipeline. DB skills win on name conflicts.
- **Git failure retry handling**: If the git clone/pull fails, the task is moved to the scheduled column for retry via the existing retry mechanism. After exhausting retries, the task moves to the review column for user intervention.
- **Settings UI for repository configuration**: New fields in the Agent Configuration section for the git repo URL, branch, and base path.

## Capabilities

### New Capabilities

- `git-sourced-skills`: Git repository as a skill source — clone/pull lifecycle, SKILL.md parsing, merge with DB skills, error handling and retry on git failures.

### Modified Capabilities

- `admin-settings-ui`: Add "Skills Repository" configuration fields (URL, branch, base path) to the Agent Configuration section.
- `task-worker`: Worker clones/pulls the git skills repo before each task, parses Agent Skills directories, and merges with DB skills before archive assembly.

## Impact

- **backend/worker.py**: New `refresh_git_skills()` and `parse_skills_from_directory()` functions. Modified `process_task_in_container()` to call git refresh and merge skills before archive assembly.
- **backend/main.py**: No API changes — `skills_git_repo` uses the existing settings key-value API (`PUT /api/settings`).
- **frontend/src/pages/SettingsPage.vue**: New form fields for git repo configuration in the Agent Configuration section.
- **Dependencies**: `git` must be available on the worker's PATH (already present in the backend Docker image for SSH key functionality).
- **No database migration**: Uses existing `Setting` model with a new key.
- **No container changes**: Git-sourced skills are injected via the same `put_archive()` pipeline as DB skills.
