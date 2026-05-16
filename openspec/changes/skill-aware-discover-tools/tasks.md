## 1. Bump version

- [x] 1.1 Increment `VERSION` per semver (PATCH — backwards-compatible bug-fix/recovery behaviour)

## 2. Extend ToolVisibilityContext

- [x] 2.1 Add `installed_skills: dict[str, str] = field(default_factory=dict)` to `ToolVisibilityContext` in `task-runner/tool_registry.py`
- [x] 2.2 Add a helper (e.g. `scan_installed_skills(skills_root: str = "/workspace/skills") -> dict[str, str]`) that returns `{name: absolute_path_to_SKILL.md}` for every `*/SKILL.md` under `skills_root`, returning an empty dict if the directory is missing

## 3. Make discover_tools skill-aware

- [x] 3.1 In `discover_tools`, after the existing `always_on_tools` / `all_known_tools` checks, partition the residual "would be Not found" names: those matching a key in `installed_skills` go to `loaded_skills`, the rest stay in `not_found`
- [x] 3.2 For each name in `loaded_skills`, read the corresponding `SKILL.md` synchronously; on read failure (`OSError`, `FileNotFoundError`) reclassify the name as `Not found` and do not raise
- [x] 3.3 Build a `Loaded skill: <names>` clause followed by `--- <absolute_path> ---\n<content>\n--- end skill ---` blocks in the order the names were passed, joined with one blank line between blocks
- [x] 3.4 Update the clause assembly to emit clauses in the order `Enabled` → `Already enabled (always-on)` → `Loaded skill` → `Not found`, joined by `". "`, with each clause omitted when its bucket is empty
- [x] 3.5 Update the `discover_tools` docstring to mention that names matching installed skills will be loaded inline rather than returning `Not found`

## 4. Wire installed_skills into agent construction

- [x] 4.1 In `task-runner/main.py`, call the new scan helper at agent construction (alongside `all_known_tools` / `always_on_tools` population) and pass the result into the `ToolVisibilityContext` constructor
- [x] 4.2 Log the count of installed skills loaded (info-level) so production traces show whether the recovery path is armed

## 5. Tests

- [x] 5.1 Add unit test: `installed_skills` is empty when `/workspace/skills/` does not exist (use `tmp_path`)
- [x] 5.2 Add unit test: `installed_skills` populated correctly when two skill dirs each contain `SKILL.md`
- [x] 5.3 Add unit test: `discover_tools(["tweet-publisher"])` with `tweet-publisher` only in `installed_skills` returns a single `Loaded skill:` clause with the SKILL.md contents inside the delimited block; `enabled_tools` is unchanged
- [x] 5.4 Add unit test: mixed probe `discover_tools(["list_applications", "tweet-publisher", "made_up_name"])` produces `Enabled: …. Loaded skill: …. Not found: made_up_name` in that order
- [x] 5.5 Add unit test: tool-name precedence — a name in both `all_known_tools` and `installed_skills` classifies as `Enabled`, not `Loaded skill`
- [x] 5.6 Add unit test: always-on precedence — a name in both `always_on_tools` and `installed_skills` classifies as `Already enabled (always-on)`, not `Loaded skill`
- [x] 5.7 Add unit test: SKILL.md unreadable at call time (path recorded in `installed_skills` but file removed) returns `Not found:` for that name without raising
- [x] 5.8 Add unit test: multiple skill matches in one call produce one `Loaded skill:` clause listing both names and two concatenated delimited blocks in the order the names were passed
- [x] 5.9 Run `errand/.venv/bin/python -m pytest task-runner/test_tool_registry.py -v` and confirm green; run the full task-runner test suite to confirm no regressions

## 6. Local verification

- [ ] 6.1 `docker compose -f testing/docker-compose.yml up --build` — start the stack
- [ ] 6.2 Trigger a task that mounts at least one skill into `/workspace/skills/` and observe a tool-call log entry showing the model probing a skill name through `discover_tools` returning a `Loaded skill:` clause (can be forced by running a task with a model that previously failed this way, or by inspecting the unit-test fixtures)
- [ ] 6.3 Confirm no regression on a task that does not probe skill names: `Loaded skill:` clause must be absent from `discover_tools` results

## 7. Commit, push, PR

- [ ] 7.1 Create feature branch `skill-aware-discover-tools` from `main`
- [ ] 7.2 Commit changes with a clear message (subject ≤ 72 chars, body explaining the failure mode and the recovery behaviour)
- [ ] 7.3 Push and open the PR; wait for CI to build images + Helm chart
- [ ] 7.4 Verify the built image runs on Kubernetes (ArgoCD sync or `helm upgrade --dry-run`) and a smoke task succeeds before merging
