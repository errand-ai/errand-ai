# Tasks — shared-cloud-workspace

## 1. Spike: rclone serve nfs viability (gates everything below)

- [x] 1.1 Stand up `rclone serve nfs` against a test Google Drive folder (VFS cache full, poll-interval 15s, skip-gdocs) in the dev cluster or locally, and mount it from 3+ containers concurrently doing mixed read/write; record failures and throughput — PASS (mount/RW/round-trip work; concurrency ceiling was Drive `403` quota on rclone's *shared* client_id, not the NFS layer; see design.md Spike Results F1/F5)
- [x] 1.2 Measure human-edit→mount visibility latency on Google Drive and OneDrive (delta polling); verify OneDrive delta behavior on a realistic folder shape — PARTIAL (Drive only; poll loop confirmed running at ~60s cadence not 15s — F6; end-to-end latency pending prod re-validation; OneDrive deferred per decision)
- [x] 1.3 Kill the gateway with pending write-backs and verify queued uploads recover from the persistent cache dir on restart — PASS (hard SIGKILL with `uploadsQueued:1`; new pod resumed upload from cache PVC; zero data loss)
- [x] 1.4 Verify runtime token rotation via `rclone rc config/update` against a live serve process (no restart, operations continue) — PASS (config applied live, no serve restart, in-flight mount undisturbed; writable-config + explicit-`token` constraints recorded — F4)
- [x] 1.5 Record spike verdict in design.md (proceed with `serve nfs`, or switch to the ganesha-over-`rclone mount` fallback) — do not proceed to section 4 until recorded — VERDICT: PROCEED with `serve nfs` + fixes; 6 findings folded into design.md and specs

## 2. Version, branch, and data model

- [x] 2.1 Create feature branch and bump VERSION (minor) — branch `shared-cloud-workspace`, VERSION 0.131.1 → 0.132.0
- [x] 2.2 Add `shared_workspace_enabled` + `shared_workspace_subpath` to TaskProfile model with Alembic migration (defaults preserve existing behavior) — model fields + migration `029`
- [x] 2.3 Expose both fields in profile CRUD API with subpath validation (relative, no `..`); update backend tests — `_validate_workspace_subpath`/`_validate_workspace_enabled` in create+update; 9 new tests; full suite (1718) green

## 3. Token plumbing

- [x] 3.1 Implement workspace-scoped bearer issuance/invalidations (opaque-bearer pattern, refresh-endpoints-only authorization, invalidated when workspace disabled) — `workspace_refresh_auth.py`: issue/renew/invalidate/invalidate_all/resolve + `require_refresh_bearer` dependency. NOTE: issuance/invalidation *call sites* deferred to §7 (workspace-enablement surface), per OQ1 decision (Valkey-bearer pattern)
- [x] 3.2 Implement OneDrive refresh endpoint through the errand-cloud relay (canonical provider name, force-refresh option, structured errors) — `onedrive_routes.py` `POST /api/onedrive/refresh-token`, registered in main.py
- [x] 3.3 Authorize the workspace bearer on the existing Google refresh endpoint; tests for bearer scoping (accepted on refresh endpoints, rejected elsewhere) — google_routes refactored to shared dependency; scoping tests in `test_workspace_refresh_auth.py`

## 4. Workspace gateway component

- [x] 4.1 Build gateway container config: rclone serve nfs entrypoint with provider-parameterized remote (drive/onedrive), VFS cache dir, poll interval, rc bound to localhost — `workspace-gateway/entrypoint.sh` + `Dockerfile.gateway` (writable-config copy per F4)
- [x] 4.2 Implement token-refresher sidecar (fetch token with workspace bearer on start + ~50min loop, push via rc `config/update`, structured failure logs, health state file/endpoint) — `workspace-gateway/refresher.py` + `Dockerfile.refresher` (explicit `token=` param, timeout-guarded rc call per F4)
- [x] 4.3 Expose gateway health (last poll, pending uploads, auth state) and a server-side `/api/workspace/status` endpoint that surfaces it — `POST /api/workspace/health` (workspace-bearer, Valkey TTL) + `GET /api/workspace/status` (admin); tests in `test_workspace_status.py`
- [ ] 4.4 Verify gateway locally with docker compose: mount from a container, read/write round-trip to a real Drive folder — **deferred to rollout (§9): needs live creds/compose run**

## 5. Runtime mount plumbing

- [x] 5.1 Add `WorkspaceMount` dataclass and optional `mounts` parameter to `ContainerRuntime.prepare()/async_prepare()`; no-mount path byte-identical to current behavior
- [x] 5.2 DockerRuntime: translate mounts to Docker volumes (NFS-backed named volume for compose gateway, bind for desktop-docker/local testing)
- [x] 5.3 KubernetesRuntime: add native `nfs:` volume (static ClusterIP target, subpath, `vers=3,nolock,soft` + conservative timeouts) and volumeMount at `/shared` — implemented as a **PVC-backed** volume per spike finding F7 (inline `nfs:` volumes can't carry mount options; the PV carrying ClusterIP + options is Helm-provisioned in §7), subPath = profile subpath
- [x] 5.4 AppleContainerRuntime: add `mounts` array to bridge create payload (contract per container-bridge-api delta spec; desktop app implementation tracked in its repo)
- [x] 5.5 TaskManager: resolve profile workspace config → mount spec per runtime; warning transcript event (`workspace_unavailable`) when profile requests workspace but deployment has none; unit tests for all three resolution paths + mounts-none regression

## 6. System skill

- [x] 6.1 Create `system-skills/shared-workspace/` SKILL.md (filesystem-first guidance, cross-provider naming rules, re-read-before-write, atomic writes, no-execute rule) — also added Dockerfile COPY line
- [x] 6.2 Register in `SYSTEM_SKILL_REGISTRY` keyed on profile workspace enablement (`shared_workspace_enabled`), `exempt_from_profile_filter=True`; tests for inject/absent/exempt conditions

## 7. Helm chart and compose

- [x] 7.1 Helm: workspace gateway Deployment (rclone + refresher sidecar), Service with configurable static ClusterIP, cache PVC, remote-config Secret, all behind `workspace.enabled=false` — `templates/workspace-gateway.yaml`; renders 0 resources when disabled, full set + static ClusterIP when enabled (helm template exit 0); also NFS PV (mountOptions per F7) + task PVC + startup bearer registration/invalidation
- [x] 7.2 Helm: NetworkPolicy restricting NFS ingress to task-runner Job labels + server; server env vars for gateway address/export when enabled — NetworkPolicy (task-runner + server pod selectors); `WORKSPACE_*` env on server-deployment
- [x] 7.3 Compose: optional workspace gateway service behind a compose profile; NFS named volume for task containers; document local setup — `workspace` profile services (gateway + refresher via shared netns) + `workspace-shared` NFS volume; `docker compose config` validates; default up unchanged
- [x] 7.4 Chart/values documentation: opt-in security trade-offs, static ClusterIP guidance, mirror-mode requirement note for desktop parity — documented in the values.yaml `workspace:` block header + compose comments (incl. node nfs-utils prereq F2)

## 8. Settings UI

- [x] 8.1 Shared Workspace settings section: read-only deployment config display, disabled-state messaging with docs link — `SharedWorkspaceCard` shipped in `@errand-ai/ui-components@0.10.0` (per the library change `add-shared-workspace-settings-card`); errand frontend consumes 0.10.0 and renders it in a dedicated **Shared Workspace** settings section (`SharedWorkspacePage.vue` + route + nav)
- [x] 8.2 Health readout wired to `/api/workspace/status` with degraded-state styling; frontend tests — health readout is part of `SharedWorkspaceCard` (0.10.0); in-repo `WorkspaceStatus`/`WorkspaceGatewayHealth` types + `fetchWorkspaceStatus` tests; `getWorkspaceStatus` provided via the library's `createDirectApi`
- [x] 8.3 Task profile settings: workspace enable toggle + subpath field with validation — toggle + subpath controls shipped in `TaskProfileEditModal` (0.10.0); `TaskProfile` type carries `shared_workspace_enabled`/`shared_workspace_subpath`; backend validation enforced in §2.3

> NOTE: The settings cards and the task-profile add/edit form are owned by the external `@errand-ai/ui-components` package (this repo's settings pages are thin wrappers). Section 8's UI rendering is therefore implemented in that repo against the API/data contract delivered here — the same repo-split the design established for the desktop app (`container-bridge-api`). Marked `[~]` = in-repo contract complete, external UI pending.

## 9. Verification and rollout

- [ ] 9.1 Local end-to-end: docker compose up with gateway profile; workspace-enabled task reads, modifies, and writes back a file; human edit mid-task visible to the task
- [x] 9.2 Backend + frontend test suites green; new tests cover mounts-none regression paths
- [x] 9.3 Push branch, PR, verify CI images/chart; deploy to dev cluster with `workspace.enabled=true` and run the same end-to-end against real Drive and OneDrive folders — **Drive validated on dev cluster (task listed the whole Drive root via `/shared`); OneDrive descoped to a later change per the "Drive only for now" decision**
- [ ] 9.4 Enable workspace profile for nginx-log-analyzer and blogs-to-process tasks; update their prompts/skills to `/shared` paths; confirm the next scheduled runs produce correctly named files (no new "Untitled")
- [x] 9.5 Documentation: feature guide with security trade-offs, conflict model (last-write-wins + version history), provider setup for Drive and OneDrive — **published in errand-sh (`Integrations/shared-workspace.mdx`, merged)**
