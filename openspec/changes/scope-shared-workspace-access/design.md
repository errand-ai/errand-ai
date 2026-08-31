## Context

`/shared` is the only non-disposable thing a task touches. Everything else lives in a container that is destroyed at the end of the run; `/shared` is a PVC over NFS to the workspace gateway under Kubernetes, or a host bind mount under Docker and Apple, and the gateway syncs it to the user's Google Drive or OneDrive.

Two of the three axes of control already exist on the profile: `shared_workspace_enabled` decides whether the workspace is mounted at all, and `shared_workspace_subpath` decides which subtree, validated against `..` traversal. The third — what the task may *do* inside the mount — has no representation, so a profile that only reads a spreadsheet is granted the same write access as one whose job is to produce files.

The caller shapes the threat. The task LLM routinely acts on content it fetched moments earlier, so the realistic failure is not a malicious operator but an agent induced to overwrite files that happen to be in scope, or to read one into the conversation from where it can leave via `slack_message`, `send_email` or `post_tweet`.

One piece of the mechanism is already present and inert: `WorkspaceMount` carries `read_only: bool = False`, which no runtime reads and no setting populates.

## Goals / Non-Goals

**Goals:**

- A profile can declare that its workspace mount is read-only, and that declaration is enforced by the container runtime rather than by the task-runner.
- Enforcement is uniform across Docker, Kubernetes and Apple, or the mount is refused.
- A write refused because the mount is read-only is legible in the transcript as a policy decision, not as a disk error.
- Existing profiles are unaffected.

**Non-Goals:**

- Making read-write safe. A read-write profile can still damage its own subtree; bounding that needs per-operation confirmation or snapshotting and is a much larger change.
- Path restrictions on `write_file` / `edit_file` / `read_file`. See the decision below — alone they enforce nothing.
- Restricting `execute_command`. Rejected in `address-security-review-findings` and still rejected: running agent-authored commands in a disposable container is the product.
- Read-only *sub-paths* within one mount. One flag for the whole mount; a profile needing finer granularity should use `shared_workspace_subpath`.

## Decisions

**Enforce at the mount, not in the tools.** The originating finding proposed a path allowlist on the file tools. Implemented alone it enforces nothing, because `execute_command` runs arbitrary shell in the same container: `write_file("/shared/x")` would be refused while `execute_command("rm -rf /shared/*")` proceeds untouched. A control the sandboxed process can route around is not a control. A read-only bind mount or `readOnly: true` volumeMount is enforced by the kernel and refuses `write_file`, `execute_command`, and anything the agent invents, identically and without the task-runner participating.

The alternative — restricting the file tools *and* `execute_command` — was considered and rejected. It would require parsing arbitrary shell to determine what a command touches, which is not decidable in general, and it would remove the capability errand exists to provide.

**A profile column, not a global setting.** Read-only-ness is a property of what a profile does, not of the deployment. A researcher profile reads; a report-generator writes. A global switch would force the deployment to the permissive setting as soon as any one profile needs to write, which is the same failure mode the empty-by-default `url_fetch_allowlist` avoids by being explicit per-exception.

**Populate the existing `read_only` field rather than adding a parallel mechanism.** `WorkspaceMount.read_only` already exists and is documented in the dataclass. Making it live is a smaller change than introducing a second concept, and it removes a dead field that currently reads as an implemented feature.

**Refuse to mount rather than downgrade, where a runtime cannot enforce read-only.** This mirrors the existing behaviour for subpaths: the task manager already refuses to mount when a Docker named volume cannot be scoped to the requested subpath, rather than silently mounting the whole workspace, with the reasoning recorded in-line as data-exposure. Silently granting write access to a profile that asked for read-only is the same class of error, and gets the same answer. A profile that cannot be honoured fails visibly.

**The skill change is in scope, not optional.** A read-only NFS mount surfaces a write failure as `EROFS`, which reaches the transcript as an opaque I/O error. Without telling the agent the mount may be read-only, the likely outcome is a retry loop and a task that fails with a misleading reason — turning a security improvement into a support burden. Teaching it costs a paragraph in the existing SKILL.md.

**The settings-UI toggle is in scope.** Without it the column is only reachable through the API, so the feature exists but no one can turn it on. It sits beside the two workspace controls it belongs with.

## Risks / Trade-offs

**A read-only profile whose task genuinely needs to write will fail** → That is the intended behaviour, but it must be diagnosable. Mitigated by the skill change and by requiring the runtime-level refusal to name the cause. The failure should say the mount is read-only for this profile, not surface `EROFS`.

**Apple runtime enforcement is unverified** → The bridge's container-create payload carries a `mounts` array; whether it honours a read-only flag is not established, and the bridge is the least-exercised of the three runtimes. If it cannot, the fail-closed rule applies and Apple refuses the mount, which is safe but makes the feature unavailable there. Establishing this is a task, not an assumption.

**Read-only is coarse** → A profile that needs to write one output file but read many gets no help; it must be read-write. Accepted: the alternative is per-path policy, which is the larger change this explicitly defers.

**A read-only mount does not stop exfiltration** → `read_file` can still pull any in-scope workspace file into the conversation, from where an outbound tool can send it. This change bounds *modification*, not *disclosure*; `shared_workspace_subpath` remains the only control on what is visible. Worth stating so the flag is not mistaken for a confidentiality boundary.

## Migration Plan

One additive migration: `shared_workspace_read_only` boolean, NOT NULL, default `false`. Existing rows take the default, which is today's behaviour, so no profile changes on deploy and there is nothing to backfill.

The runtime changes are inert until a profile sets the flag, so the code and the migration can land together without sequencing. Rollback is a version revert; the column can remain in place harmlessly, since a runtime that does not read it behaves exactly as before.

## Open Questions

- Does the Apple container bridge honour a read-only mount, and if not, is refusing the mount acceptable for desktop users, or should Apple be out of scope until the bridge supports it?
- Should `shared_workspace_read_only=true` also imply anything for the *output* path (`/output/result.json`)? It should not — that is container-local and unrelated — but the naming invites the confusion, and the skill text should be explicit that only `/shared` is affected.
- Is `read_only` the right name on the profile, given the UI will likely phrase it as "allow this profile to modify the workspace"? A positively-phrased column (`shared_workspace_writable`, default `true`) would read better in the UI but inverts the safe default, which is why this proposes the negative form.
