# Shared Cloud Workspace — Design

## Context

Errand tasks run in ephemeral containers with no filesystem that survives the task or reaches cloud storage. File exchange with Google Drive goes through the `gws` CLI, whose `--params`-JSON interface local LLMs consistently misuse (production logs: invented flags, `files.get`/`files upload` hallucinations, `name`/`parents` stringified out of create requests → "Untitled" files in the Drive root). OneDrive access goes through MCP tools with a similar model-capability ceiling.

Filesystem operations are the interface weak models handle reliably. This design gives opted-in tasks a `/shared` mount that is a **live view of a designated Google Drive or OneDrive folder**, with humans free to edit the same folder concurrently from the cloud UI or their desktop sync client.

Current state relevant to the design:

- `ContainerRuntime` (`errand/container_runtime.py`) has three implementations. DockerRuntime uses zero volumes today (files injected via `put_archive`, output read from logs). KubernetesRuntime builds Jobs with `emptyDir` + ConfigMap volumes. AppleContainerRuntime POSTs a JSON payload to the Errand-Desktop bridge API.
- The task-runner already has a mid-task Google token refresh mechanism (`POST /api/google/refresh-token`, per-task opaque bearer in Valkey). OneDrive has no equivalent.
- Task profiles (`task_profiles`) already carry per-profile execution config (`llm_timeout`, `container_image`).
- System skills (`SYSTEM_SKILL_REGISTRY`) inject SKILL.md sets conditionally per task context.

## Goals / Non-Goals

**Goals:**

- Tasks that opt in can read, modify, and write back files in a designated cloud folder using plain filesystem operations.
- Human edits made in Drive/OneDrive while a task is running become visible to the task within ~15 seconds; task writes appear in the cloud shortly after file close.
- One consistent mechanism for both Google Drive and OneDrive (identical component, config differs only in the rclone remote).
- Works on all three runtimes: Kubernetes (gateway), docker-compose (gateway), Errand-Desktop (native sync client folder via virtiofs/bind mount; gateway not required).
- Off by default; per-profile opt-in; subpath-scoped; risks documented.

**Non-Goals:**

- File locking / true concurrent-edit merging. Cloud providers offer none; the model is last-write-wins + version history (see Decisions).
- Syncing Google-native files (Docs/Sheets/Slides). They are not real files; they remain gws/API territory (`--drive-skip-gdocs`).
- Replacing the `gws` CLI or OneDrive MCP tools — they remain for API-shaped operations (sharing, search, metadata, native docs).
- Multi-gateway / per-user gateway instances. v1 is one workspace folder per errand deployment.
- RWX storage classes, NFS-Ganesha, CephFS, JuiceFS etc. — superseded by the live-gateway decision (kept as fallback, see Risks).

## Decisions

### D1. Live gateway (`rclone serve nfs`) over store-and-sync

The workspace component runs `rclone serve nfs <remote>:/<folder>` — rclone is simultaneously the NFS server and the cloud client. The cloud folder is the source of truth; the only local state is the VFS cache.

- **Why not directional inbox/outbox**: tasks need read-modify-write on the same file.
- **Why not `rclone bisync` against a canonical PVC**: any sync interval creates a stale-read → human-edit → clobbering-write-back window; bisync is also rclone's most fragile command (resync state, conflict renames). Live view shrinks the staleness window to the poll interval.
- **Why rclone at all**: the only tool with identical config/commands for both Drive and OneDrive; both backends support ChangeNotify polling (OneDrive via delta API).
- **Alternatives considered**: NFS-Ganesha exporting an RWO PVC + bisync sidecar (two components, sync lag, conflict states); ganesha exporting an `rclone mount` FUSE dir (retained as fallback, D8); object-store FUSE mounts inside task pods (impossible: distroless nonroot task image, no `/dev/fuse`).

Gateway flags (v1 baseline): `--vfs-cache-mode full`, `--cache-dir` on a PVC, `--poll-interval 15s`, `--drive-skip-gdocs`, `--rc` (localhost-only, for the token refresher), sensible `--vfs-cache-max-size`.

### D2. VFS cache on a persistent volume, not emptyDir

Write-back uploads queue in the VFS cache. If the gateway pod dies with pending uploads on an emptyDir, task output is silently lost. A small RWO PVC for `--cache-dir` makes pending writes survive restarts; rclone resumes uploads on start.

### D3. Token refresher sidecar using rclone's rc API

`rclone serve` is long-running, but errand's cloud tokens are 60-minute access tokens refreshed via errand-cloud — rclone cannot refresh them itself. A sidecar loops (~every 50 min, and on gateway start): fetch a fresh access token from an internal errand endpoint, push it into the running rclone via `rclone rc config/update`, without restarting the server. **Validated in the spike (1.4)** — `config/update` mutates the running backend with no NFS-server restart and no disruption to in-flight mounts. Two operational constraints the spike surfaced (F4): (1) `config/update` persists to the rclone config file, so the gateway must copy its config from the Secret to a **writable** volume at startup (a read-only Secret mount returns HTTP 500); (2) the refresher must pass the token explicitly as `parameters={"token": …}` and guard the rc call with a timeout — a bare `config/update` makes rclone attempt an interactive OAuth webserver, and backend re-init can block under API throttling.

- Google: reuse the existing refresh machinery behind a workspace-scoped bearer (same Valkey-bearer pattern as the per-task `ERRAND_API_KEY`, but issued for the gateway with a non-expiring/renewed TTL).
- OneDrive: requires a new refresh endpoint (`cloud-storage-oauth` capability change) — this closes the known "OneDrive mid-task refresh not implemented" gap.
- **Alternative considered**: user-supplied standalone rclone OAuth refresh token in a k8s Secret. Rejected as v1 default: a long-lived refresh token in a Secret is a stronger credential than errand otherwise persists, requires a second OAuth consent, and can silently diverge from errand's connection state. (Documented as an escape hatch for air-gapped-from-errand-cloud setups.)

### D4. Task pods mount via the k8s-native `nfs:` volume against a fixed ClusterIP

No CSI driver dependency. kubelet performs NFS mounts from the node's network namespace, where cluster DNS is typically unavailable — therefore the gateway Service reserves a **static ClusterIP** (Helm value, default chosen from the service CIDR) and the volume spec uses the IP, with `mountOptions: [vers=3, nolock, soft, timeo=…]` (`nolock`: no NLM; `soft` so a dead gateway fails I/O instead of hanging pods indefinitely — see R3).
- **Node prerequisite (spike F2)**: the kubelet mounts NFS via the host's `mount.nfs` helper, so every node that can schedule task Jobs MUST have `nfs-utils` installed (the `nfs` kernel module alone is insufficient). This is a documented cluster prerequisite; a task Job on a node without it fails to mount `/shared`.
- **PV, not inline (spike F7)**: pod-inline `nfs:` volumes cannot carry `mountOptions`, so the required `vers=3,nolock,soft,timeo=…` must be expressed on a **PersistentVolume** (static, CSI-free) that the Job's PVC binds, or via StorageClass `mountOptions`. KubernetesRuntime therefore references a PV, not an inline volume.
- **Restart caveat (spike F3)**: a gateway pod replacement invalidates NFS file handles held by mounted task pods (`ESTALE`); with `soft`, in-flight tasks see I/O errors rather than transparent recovery. The gateway lifecycle is decoupled from the server roll for exactly this reason.
- NFSv3 has no authentication → a NetworkPolicy restricts gateway ingress to task-runner pods (matched by the existing job label) and the errand server.
- docker-compose: a named volume with `driver_opts: type=nfs` pointing at the gateway service; same gateway container image and config.
- Errand-Desktop: native Drive/OneDrive sync client already provides the live view locally; the bridge mounts the local sync subfolder into the container via virtiofs (`mounts` field in the bridge create payload). Gateway not deployed. Caveat documented: Google Drive/OneDrive on macOS must be in "mirrored" mode for the shared subfolder (File Provider dataless placeholders do not materialize reliably through virtiofs).

### D5. Mount plumbing through `ContainerRuntime`

`prepare()`/`async_prepare()` gain `mounts: list[WorkspaceMount] | None` where `WorkspaceMount` is a small dataclass: `container_path` (always `/shared` in v1), plus per-runtime source data resolved by the task manager (host path for docker/apple; NFS server+export+subpath for k8s/compose). Runtimes translate: DockerRuntime → `volumes`/`mounts` kwarg; KubernetesRuntime → volume + volumeMount on the Job; AppleContainerRuntime → `mounts` array in the bridge payload. The task manager resolves profile config → mount spec; tasks without the profile flag get exactly today's behavior.

### D6. Conflict model: last-write-wins, made survivable

No locking exists end-to-end (Drive/OneDrive have none; rclone's NFSv3 has no NLM). The design makes this safe-enough rather than pretending otherwise:

1. Change-polling keeps reads fresh — targeted at ~15s, but the spike (F6) observed a **~60s** effective cadence on Google Drive despite `--poll-interval 15s`. Treat the freshness window as ≈ the effective poll cadence (≥60s until re-validated/tuned), which makes points 2–4 more important, not less.
2. The workspace system skill instructs agents: re-read immediately before write-back, keep read-modify-write windows short, write atomically (temp name → rename).
3. Both providers keep version history — a clobbered human edit is recoverable from the provider UI.
4. Parallel tasks that target the same file are an application-scheduling concern (documented; not solved by storage).

### D7. Per-profile opt-in with subpath scoping

`task_profiles` gains `shared_workspace_enabled: bool` (default false) and `shared_workspace_subpath: str | None`. The mounted source is `<workspace root>/<subpath>` — a profile can be confined to a subdirectory of the workspace folder. Security consequences are accepted and documented: within a mounted subpath, participating tasks share visibility (all task containers run UID 65532; isolation between them is by subpath scoping only). The platform never executes or loads instructions/skills from `/shared` content.

### D8. Explicit spike gates implementation; ganesha-over-`rclone mount` is the fallback

`rclone serve nfs` is the youngest component in the chain (v1.65+, Go NFS library, NFSv3). A spike task precedes implementation and must demonstrate: (a) ≥3 concurrent task pods doing mixed read/write through one gateway; (b) human-edit→container visibility latency on both Drive and OneDrive; (c) pod kill with pending write-backs → uploads recovered from cache PVC on restart; (d) OneDrive delta-polling behavior on the real folder shape. If it fails, the fallback keeps every task-facing semantic: an NFS-Ganesha container exporting an `rclone mount` FUSE directory from a shared-process-namespace sidecar (same VFS cache/poll flags, mature NFS layer, cost: FUSE-privileged gateway pod — acceptable, it is our pod, not a task pod).

**Verdict (2026-07-20): PROCEED with `rclone serve nfs`.** The spike ran against a live Google Drive folder on the dev cluster (single-node k3s) using `rclone/rclone:1.68`. Core mechanics all held; the failures observed were attributable to the *shared* rclone OAuth `client_id`'s Drive API quota (not the NFS layer) and to node/config provisioning gaps that are now folded into the specs. Full results below (§ Spike Results). The ganesha fallback is **retained but not selected** — it uses `rclone mount` underneath and would hit the identical Drive quota ceiling, so it does not address the one real risk the spike surfaced.

## Spike Results (D8 acceptance — 2026-07-20)

Ran on the dev cluster (`devops-consultants`, single-node k3s v1.32, CentOS 7) in a throwaway `workspace-spike` namespace: `rclone/rclone:1.68` running `serve nfs gdrive-spike:Errand-spike` with `--vfs-cache-mode full`, cache on a `local-path` PVC, `--poll-interval 15s`, `--drive-skip-gdocs`, `--rc` on localhost. Task-side mounts were exercised from privileged Alpine pods self-mounting `mount -t nfs -o vers=3,nolock,tcp,port=2049,mountport=2049,soft,timeo=…` (see Finding F2 for why not kubelet-native).

**Per-test outcome:**

- **1.1 Concurrent read/write — PASS (with a quota caveat).** Mount/read/write/round-trip to Drive all work; a file written through the mount appeared in Drive with the exact name. Two concurrent clients completed 30/30 writes each with 0 errors. Under 4 aggressive concurrent writers (~160 small writes + per-op `ls`/`stat` in ~40s) the gateway returned I/O errors and the rclone process crashed once (exit 2) — **root cause was Google Drive `403 rateLimitExceeded`** on rclone's *shared default* `client_id` (no dedicated `client_id` was configured), not the NFS layer. Production uses errand-cloud's own OAuth client + quota, so this specific ceiling does not transfer; a clean concurrency re-run with a dedicated `client_id` is recommended before GA (see F5, F7).
- **1.2 Human-edit → visibility latency — PARTIAL.** The rclone ChangeNotify poll loop is confirmed running ("Checking for changes on remote"), but at a **60s cadence despite `--poll-interval 15s`**. End-to-end human-edit latency was not measured: the external Drive writes used to simulate a human edit were themselves throttle-killed by the shared-quota depletion. Poll mechanism works; the "~15s freshness" figure is unverified and must be re-validated in production against errand's own quota (F6).
- **1.3 Write-back recovery — PASS (zero data loss).** With `--vfs-write-back 60s`, a file written through the mount showed `vfs/stats uploadsQueued:1` and was confirmed **absent from Drive**. The gateway pod was then hard-killed (`--grace-period=0 --force`, SIGKILL — simulating a crash). The replacement pod mounted the same cache PVC, the cache item persisted across pods (`/cache/vfs/…/recovery-*.txt`, 16 bytes), and the queued upload completed — file landed in Drive. Validates D2.
- **1.4 Live token rotation — PASS.** `rclone rc config/update` applied a change to the *running* backend config (visible in `config/dump`) with **no restart of the NFS server** (the single "NFS Server running" log line was unchanged), and an in-flight mount kept serving reads/writes across the update. Caveats folded into F4.

**Findings folded into the specs/design (the "6 findings"):**

- **F1 — `serve nfs` can crash under an error storm.** rclone exited (code 2) during the concurrent-load + 403 storm. Mitigation is already the architecture (gateway is a Deployment → auto-restarts; cache PVC → no data loss on restart) plus health surfacing; no change to the decision, but the gateway MUST run as a restart-managed Deployment with the persistent cache, never a bare Pod.
- **F2 — nodes need `nfs-utils`.** The k3s node had no `mount.nfs` (the `nfs` kernel module loads fine). The kubelet-native `nfs:` volume (D4) shells out to the host `mount.nfs`, so **task Jobs cannot mount without `nfs-utils` on every node** — a documented node prerequisite. Reflected in `k8s-task-execution` and `helm-deployment` specs.
- **F3 — a gateway restart invalidates live NFS handles.** After a gateway pod replacement, already-mounted clients got `Stale file handle` (ESTALE); with `soft` they surface I/O errors rather than auto-recovering. This is the concrete reason the gateway lifecycle must be decoupled from the server roll (already in `helm-deployment`, now sharpened) and why task-facing docs must state that a gateway restart mid-task fails that task's `/shared` I/O.
- **F4 — the token-refresher needs a writable config and must push `token=`.** `config/update` persists to the rclone config file, so a read-only Secret mount returns HTTP 500 — the gateway must copy the config to a writable volume at startup (validated). The refresher must pass `parameters={"token": …}` explicitly; a bare `config/update` made rclone attempt an interactive OAuth webserver (`bind 127.0.0.1:53682`). The rc call must be timeout-guarded (it can block re-initialising the backend under API throttling). Reflected in `workspace-gateway` and `cloud-storage-oauth`.
- **F5 — Drive API quota, not the NFS server, is the concurrency ceiling.** Every NFS metadata op can fan out to a Drive API call; the *shared* `client_id` is exhausted quickly. Production must use a dedicated OAuth `client_id` (errand-cloud's), raise `actimeo`/`--dir-cache-time`/`--attr-timeout` to serve stat/readdir from cache, and tune `--drive-pacer-*`. Documented in `helm-deployment` values guidance.
- **F6 — observed change-poll cadence was 60s, not 15s.** Directly affects the D6 "~15s freshness" claim. Treat freshness as ≈ the effective poll cadence (≥60s observed) until re-validated; the conflict model's re-read-before-write discipline matters more, not less.
- **F7 (bonus) — inline `nfs:` volumes can't carry mount options.** `vers=3,nolock,soft,timeo=…` must live on a **PersistentVolume** (or StorageClass `mountOptions`), not a pod-inline `nfs:` volume. The `k8s-task-execution` spec is corrected from "inline `nfs:` volume" to "PV-backed `nfs:` volume (or CSI-free static PV) so mount options apply."
- **F9 (rollout) — the gateway must be authenticated at *startup*, not just while running.** A rolled/restarted gateway pod copies its rclone config from the Secret, whose access token may be long expired (the refresher only keeps the *running* rclone fresh via the rc API — it never writes back to the Secret). Serving the remote **root** authenticates immediately (resolve root directory ID), so a stale startup token makes rclone crash-loop with `couldn't fetch token: unauthorized_client` when the remote can't self-refresh (a subfolder deferred this and masked it). Fix: an **init container** (the refresher image in `init` mode) fetches a fresh token from errand and writes it into the writable config before `rclone serve` starts; the entrypoint's config copy became conditional so it doesn't clobber the init's fresh token. This makes restarts robust and keeps rclone fully dependent on errand for tokens (never its own OAuth), matching D3.
- **F8 (rollout) — NFS mounts must force `proto=tcp`.** On the dev-cluster rollout, task Job mounts hung with `mount.nfs: Connection timed out` even though the gateway was reachable on TCP 2049. Cause: `rclone serve nfs` is **TCP-only**, but the node's NFS client (CentOS 7 kubelet) defaults NFSv3 to **UDP**, which rclone never answers. Reproduced from the node: the mount times out without `proto`, and succeeds immediately with `proto=tcp,mountproto=tcp`. Fix: add `proto=tcp`/`mountproto=tcp` to the default `workspace.nfsMountOptions` and the compose NFS volume opts. (The spike missed this because its Alpine client explicitly passed `tcp`.) Note: on ArgoCD-managed clusters the PV mountOptions must be changed via the chart/Git source — a manual `kubectl patch` is reverted by auto-sync.

## Risks / Trade-offs

- **[R1] `rclone serve nfs` immaturity under concurrent clients** → D8 spike before implementation; documented fallback with identical task-facing contract.
- **[R2] Cloud/auth outage becomes a mid-task failure mode** → `--vfs-cache-mode full` keeps cached reads and queues writes with retry; `soft` mount fails uncached I/O with errors rather than wedging pods; gateway health surfaced in settings UI (last poll, pending uploads, auth state) and in structured logs for Loki alerting.
- **[R3] `soft` NFS mounts can theoretically corrupt on retry-exhaustion mid-write** → acceptable for this workload (whole-file writes of reports/documents, provider version history); tune `timeo/retrans` conservatively; documented.
- **[R4] Cross-task / cross-user data visibility within the mounted subpath** → opt-in per profile, subpath scoping, prominent documentation; ephemeral guarantee intact for everything else. No-execute rule: nothing under `/shared` is ever run or loaded as instructions by the platform.
- **[R5] Prompt-injected task exfiltrates or tampers with workspace files** → same blast-radius controls as R4; provider version history for recovery; recommend a dedicated workspace folder (not Drive root) so exposure is deliberate.
- **[R6] OneDrive filename restrictions break cross-provider parity** (`" * : < > ? / \ |`, trailing dots/spaces, reserved names, case-insensitivity) → workspace system skill mandates a safe naming convention; gateway logs rejects; docs.
- **[R7] Token refresher failure silently kills the gateway after ≤60 min** → refresher failures set gateway health state (surfaced in UI); rclone retries queue writes until token returns; Loki-alertable log lines.
- **[R8] Agent dumps huge artifacts into `/shared`** → `--vfs-cache-max-size`, documented quota guidance, provider-side quota is the ultimate backstop.
- **[R9] macOS File Provider dataless files on desktop** → require/document "mirror" mode for the shared subfolder.
- **[R10] Static ClusterIP allocation can collide or be unavailable on some clusters** → Helm value with validation guidance; documented.

## Migration Plan

1. Ship gateway + mounts behind default-off Helm values (`workspace.enabled=false`) and profile flag defaults (false). No migration impact on existing deployments; Alembic migration only adds nullable/default-false profile columns.
2. Enable in the dev cluster; run the D8 spike acceptance checks against the deployed gateway.
3. Enable per-profile for the two known consumers (nginx-log-analyzer, blogs-to-process) and update those task prompts/skills to use `/shared`.
4. Rollback: disable profile flags (tasks revert to gws/MCP paths), then `workspace.enabled=false`. The cloud folder is untouched — no data migration in either direction; the cache PVC can be deleted after pending uploads drain (health readout shows zero pending).

## Open Questions

- **OQ1**: Exact identity for gateway token fetch — reuse the Valkey-bearer pattern with a renewing TTL, or introduce a first-class "service credential" concept? (Leaning bearer-pattern for v1; decide during token-refresher implementation.)
- **OQ2**: Should compose/desktop installs without errand-cloud (fully local auth) get the rclone-own-OAuth escape hatch in v1, or defer? (Leaning defer; document limitation.)
- **OQ3**: Whether `workspace-settings-ui` health data comes from the rc API proxied via errand-server or from a lightweight status file the refresher writes — decide when building the settings surface.
