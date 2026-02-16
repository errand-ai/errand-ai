## 1. Settings & Configuration

- [x] 1.1 Add `skills_git_repo` to the `read_settings()` function in `backend/worker.py` — read the setting from the DB and include it in the returned dict as `{"url": ..., "branch": ..., "path": ...}`

## 2. Git Clone/Pull Lifecycle

- [x] 2.1 Add `refresh_git_clone(repo_url, branch, ssh_private_key)` function to `backend/worker.py` — clones to `/tmp/content-manager-skills-<sha256(url)[:12]>/` if not present, otherwise runs `git pull --ff-only`. Uses `GIT_SSH_COMMAND` with the SSH key written to a temp file. Returns the clone directory path.
- [x] 2.2 Add `parse_skills_from_directory(base_path)` function to `backend/worker.py` — scans for subdirectories containing `SKILL.md`, parses YAML frontmatter (name, description) and markdown body (instructions), reads files from `scripts/`, `references/`, `assets/` subdirectories. Returns `list[dict]` matching the `build_skills_archive()` input format.
- [x] 2.3 Add `merge_skills(db_skills, git_skills)` function to `backend/worker.py` — combines both lists, DB wins on name conflicts, logs a warning for conflicts. Returns merged `list[dict]`.

## 3. Worker Integration

- [x] 3.1 Update `process_task_in_container()` in `backend/worker.py` — after `read_settings()`, if `skills_git_repo` is configured, call `refresh_git_clone()` then `parse_skills_from_directory()`, then `merge_skills()` with DB skills. Pass merged list to `build_skills_archive()` and `build_skill_manifest()`.
- [x] 3.2 Add git failure error handling — catch `subprocess.CalledProcessError` (and similar) from `refresh_git_clone()`, route through `_schedule_retry()` with the git error message in `output`. After max retries, move to `review`.

## 4. Backend Tests

- [x] 4.1 Write tests for `refresh_git_clone()` — first call clones, second call pulls, SSH key used when present, branch checkout
- [x] 4.2 Write tests for `parse_skills_from_directory()` — parses SKILL.md with frontmatter and files, skips directories without SKILL.md, handles empty dirs
- [x] 4.3 Write tests for `merge_skills()` — no conflicts merges all, DB wins on conflict with warning log, empty lists handled
- [x] 4.4 Write integration test for git failure retry — mock subprocess to fail, verify task moves to scheduled then to review after max retries

## 5. Frontend — Skills Repository UI

- [x] 5.1 Add "Skills Repository" section to `SettingsPage.vue` in the Agent Configuration group after Skills — three text inputs (Repository URL, Branch, Skills Path) with a Save button
- [x] 5.2 Load `skills_git_repo` from `GET /api/settings` on mount and populate the form fields
- [x] 5.3 Save handler: assemble the JSON object (omit empty branch/path), send via `PUT /api/settings` with `{"skills_git_repo": ...}`. Clear URL sends `{"skills_git_repo": null}`.
- [x] 5.4 Write frontend tests for the Skills Repository section — load existing config, save with all fields, save with URL only, clear config

## 6. Verification

- [x] 6.1 Run full backend test suite and verify all tests pass
- [x] 6.2 Run full frontend test suite and verify all tests pass
