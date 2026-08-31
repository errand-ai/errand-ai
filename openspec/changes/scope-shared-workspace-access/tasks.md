## 1. Branch and version

- [ ] 1.1 Create branch `scope-shared-workspace-access` from an up-to-date `main`
- [ ] 1.2 Bump `VERSION` (minor — a new profile field and a behaviour change to mounting)

## 2. Establish what the Apple bridge can do

First, because the answer decides whether section 5 is implementation or a documented refusal, and finding out late means reworking the runtime tests.

- [ ] 2.1 Determine whether the container bridge's create payload honours a read-only mount. Read the bridge API contract rather than inferring it from `container_runtime.py`
- [ ] 2.2 Record the answer in `design.md` under Open Questions, replacing the question with the finding either way

## 3. Profile field

- [ ] 3.1 Write failing tests: a profile round-trips `shared_workspace_read_only` through the CRUD API; the default is `false`; the value persists while `shared_workspace_enabled` is `false`
- [ ] 3.2 Add `shared_workspace_read_only` to the `TaskProfile` model
- [ ] 3.3 Add the Alembic migration (boolean, NOT NULL, server default `false`)
- [ ] 3.4 Expose the field through the profile CRUD API, following the handling of the two existing workspace fields
- [ ] 3.5 Verify against a populated database that existing profiles take the default and no other column is touched

## 4. Mount construction

- [ ] 4.1 Write a failing test: a profile with `shared_workspace_read_only=true` produces a `WorkspaceMount` with `read_only=True`
- [ ] 4.2 Populate `WorkspaceMount.read_only` from the profile in the task manager's mount construction
- [ ] 4.3 Confirm the field is threaded through both the Kubernetes (PVC) and host-path branches, not just the one exercised by the local runtime

## 5. Runtime enforcement

The security property lives here. Everything above is plumbing; if a runtime attaches the mount read-write, the feature is decorative.

- [ ] 5.1 Write failing tests per runtime: a read-only mount produces a read-only bind mount (Docker) and `readOnly: true` on the volumeMount (Kubernetes)
- [ ] 5.2 Write a failing test for the fail-closed rule: a runtime that cannot enforce read-only refuses the mount rather than attaching it read-write
- [ ] 5.3 Implement read-only attachment in `DockerRuntime`
- [ ] 5.4 Implement read-only attachment in `KubernetesRuntime`
- [ ] 5.5 Implement read-only attachment in `AppleContainerRuntime`, or the refusal path if 2.1 established it cannot enforce it
- [ ] 5.6 Make the refusal message name the runtime and state that read-only enforcement is unavailable, so it is not read as a mount or network failure

## 6. Agent guidance

- [ ] 6.1 Extend the shared-workspace SKILL.md: writes under `/shared` may fail by design, report the restriction rather than retry or route around it, and the restriction applies to `/shared` only — not `/workspace` or the output path
- [ ] 6.2 Confirm the existing skill-injection tests still pass and the skill is still gated on `shared_workspace_enabled`

## 7. Settings UI

- [ ] 7.1 Write failing tests: the control appears only when the workspace is enabled, and round-trips through the API
- [ ] 7.2 Add the toggle beside the existing workspace controls, worded in terms of modifying the user's files rather than the column name
- [ ] 7.3 Frontend suite green

## 8. Verify

- [ ] 8.1 Backend and frontend suites green
- [ ] 8.2 Run a real task under a read-only profile and confirm `write_file` to `/shared` fails
- [ ] 8.3 Run the same task and confirm `execute_command` writing to `/shared` **also** fails — this is the check that distinguishes a real control from a tool-level one, and it is the reason the enforcement is at the mount
- [ ] 8.4 Confirm a read-write profile is completely unaffected
- [ ] 8.5 Confirm the agent reports the restriction rather than looping, per the skill change

## 9. Ship

- [ ] 9.1 Commit, push, open a PR
- [ ] 9.2 CI green
- [ ] 9.3 Deploy and verify a read-only profile on the built image before merging
- [ ] 9.4 Archive the change on this branch and commit it in the same PR

### Post-merge notes

- Merge and delete the branch.
- Re-verify the read-only mount on the post-archive image tag, since archiving re-triggers CI and produces a new tag.
- If 2.1 established the Apple bridge cannot enforce read-only, that gap is worth its own follow-up rather than leaving desktop users without the control indefinitely.
