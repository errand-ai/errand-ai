## Why

The `/shared` mount is the one place a task touches data that is not disposable. Everything else the task-runner can reach lives in a container that is destroyed when the task ends; `/shared` is a PVC over NFS to the workspace gateway (Kubernetes) or a host bind mount (Docker), and the gateway syncs it to the user's Google Drive or OneDrive. Writing there writes to the user's real storage.

Today a profile can choose **whether** the workspace is mounted (`shared_workspace_enabled`) and **which subtree** is mounted (`shared_workspace_subpath`, already validated against `..` traversal). Nothing chooses **what the task may do inside it**. A profile that needs to read a spreadsheet gets the same write access as one whose job is to produce files.

This matters because of who the caller is. The task LLM routinely acts on content it fetched moments earlier — a web page, an email, a Jira ticket. The realistic failure is not a malicious operator; it is an agent being talked into overwriting or deleting files that happen to be in scope, or reading a file into the conversation from where it can leave via `slack_message`, `send_email` or `post_tweet`. There is currently no way to express "this profile reads the workspace but must not change it".

This was raised as a follow-up in `address-security-review-findings` (archived) under the heading "file tools have no path allowlist", and deferred there because the blast radius of the file tools *in general* is a disposable container. That framing was right to defer, and wrong about the remedy — see below.

### Why not a path allowlist on the file tools

The originating finding proposed restricting `write_file` / `edit_file` / `read_file` (`task-runner/main.py`) to permitted paths. Implemented alone, **that control does nothing**, because `execute_command` runs arbitrary shell with `shell=True` in the same container:

```
write_file("/shared/x", ...)          →  blocked by a path check
execute_command("rm -rf /shared/*")   →  unaffected
```

Restricting `execute_command` is not available as an answer: `address-security-review-findings` rejected that explicitly, and correctly — running agent-authored commands in a disposable container is what errand *is*, not a defect in it.

A control the sandboxed process can route around is not a control. The enforcement therefore has to sit where the container cannot argue with it: **the mount**. A read-only bind mount or `readOnly: true` volumeMount is enforced by the kernel, and refuses `write_file`, `execute_command`, and anything else the agent invents, identically.

Conveniently, the data model already anticipates this. `WorkspaceMount` (`errand/container_runtime.py`) carries a `read_only: bool = False` field that **no runtime reads and no setting populates** — dead since it was introduced. This change makes it real.

## What Changes

- Add `shared_workspace_read_only` to `task_profiles` (boolean, NOT NULL, default `false`), exposed through the existing profile CRUD API and settings UI alongside the enabled/subpath fields it belongs with.
- Populate `WorkspaceMount.read_only` from that profile field in the task manager.
- Honour `read_only` in every runtime that mounts the workspace: Docker (`ro` bind mount), Kubernetes (`readOnly: true` on the volumeMount), and Apple. A runtime that cannot enforce it SHALL refuse to mount rather than mount read-write — the same fail-closed posture the existing code already takes when a Docker named volume cannot honour a requested subpath.
- Teach the shared-workspace system skill that the mount may be read-only, so the agent reports "the workspace is read-only for this profile" instead of retrying a write and reporting a confusing I/O error.
- Default `false`, so no existing profile changes behaviour.

## Capabilities

### New Capabilities

None. Every change extends an existing capability.

### Modified Capabilities

- `task-profile-model`: a third shared-workspace field, following the same validation and CRUD patterns as `shared_workspace_enabled` / `shared_workspace_subpath`.
- `container-runtime`: mounts honour `read_only`, and refuse rather than downgrade where they cannot.
- `task-profile-settings-ui`: the toggle, next to the existing workspace controls.
- `system-skill-shared-workspace`: the skill explains the read-only case.

## Impact

- **Code**: `errand/models.py` + an Alembic migration, `errand/task_manager.py` (mount construction), `errand/container_runtime.py` (all three runtimes), `frontend/` (profile settings card), `system-skills/cloud-storage/`.
- **Breaking**: none. The column defaults to `false`, which is exactly today's behaviour.
- **Risk**: a profile marked read-only whose task genuinely needs to write will fail. That is the point, but the failure must name the cause — an NFS `EROFS` surfacing as an opaque error in a task transcript is the likely support burden, which is why the skill change is in scope rather than optional.
- **Not addressed**: a read-write profile can still damage its own subtree. Bounding that needs per-operation confirmation or snapshotting, which is a different and much larger change. This one makes "read-only" expressible; it does not make "read-write" safe.
- **Explicitly not addressed**: path restrictions on the file tools, for the reason given above. If a future change revisits it, it must cover `execute_command` in the same breath or it is not a security control.
