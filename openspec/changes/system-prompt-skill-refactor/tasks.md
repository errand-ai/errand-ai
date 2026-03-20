## 1. System Skill Files

- [ ] 1.1 Create `cloud-storage/cloud-storage/SKILL.md` with cloud storage usage instructions (operations, path syntax, ETag concurrency, error handling) — content extracted from `CLOUD_STORAGE_INSTRUCTIONS` constant
- [ ] 1.2 Create `hindsight/hindsight-memory/SKILL.md` with Hindsight usage instructions (recall at task start, retain at task end, reflect for analysis)
- [ ] 1.3 Create `repo-context/repo-context/SKILL.md` with repo context discovery instructions (CLAUDE.md, commands, repo-level skills) — content extracted from `REPO_CONTEXT_INSTRUCTIONS` constant
- [ ] 1.4 Add all system skill files to task-runner Dockerfile at `/opt/system-skills/`
- [ ] 1.5 Add all system skill files to main Dockerfile (errand server) at `/app/system-skills/`

## 2. System Skills Registry

- [ ] 2.1 Implement `SYSTEM_SKILL_REGISTRY` in `task_manager.py` — list of entries with name, path, and condition function
- [ ] 2.2 Implement `load_system_skills(context: dict)` function that evaluates registry conditions and reads matching skill sets from `/app/system-skills/`
- [ ] 2.3 Wire `load_system_skills()` into task preparation: build context dict from task state (google_token, cloud_storage_injected, hindsight_url), call loader, merge results

## 3. System Prompt Simplification

- [ ] 3.1 Remove `CLOUD_STORAGE_INSTRUCTIONS` constant and its conditional append from `_process_task()` / prompt assembly
- [ ] 3.2 Remove `REPO_CONTEXT_INSTRUCTIONS` constant and its unconditional append from prompt assembly
- [ ] 3.3 Remove `recall_from_hindsight()` function and the "Relevant Context from Memory" section from prompt assembly
- [ ] 3.4 Remove the "Persistent Memory (Hindsight)" inline instructions section from prompt assembly
- [ ] 3.5 Update prompt assembly to produce: base prompt + skill manifest only (the manifest already exists from `build_skill_manifest()`)

## 4. Skill Merge Update

- [ ] 4.1 Update `merge_skills()` to accept a third `system_skills` parameter and implement three-way merge (DB > git > system)
- [ ] 4.2 Update the call site in task preparation to pass system skills from the registry loader

## 5. Tests

- [ ] 5.1 Add tests for `SYSTEM_SKILL_REGISTRY` condition evaluation with various context combinations
- [ ] 5.2 Add tests for `load_system_skills()` — filesystem reading, missing directories, skill parsing
- [ ] 5.3 Update system prompt assembly tests to verify no inline instruction blocks remain
- [ ] 5.4 Add tests verifying Hindsight prefetch is removed (no HTTP calls during prompt assembly)
- [ ] 5.5 Update skill merge tests for three-way merge with system skills

## 6. Documentation

- [ ] 6.1 Bump VERSION file (minor version)
- [ ] 6.2 Update CLAUDE.md: document system skills pattern, remove references to inline prompt sections
