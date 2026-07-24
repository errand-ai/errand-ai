## Context

The shared `@errand-ai/ui-components` settings cards were adopted into errand's Settings pages (Waves 1–2). On a **standalone** errand-server (the user's deployment, and the local docker-compose stack) three problems surfaced, verified via code, Grafana production logs, live API, and live Playwright:

1. Settings cards render the raw `{value,…}` envelope / blank values (library defect — companion change).
2. The **Cloud storage** card errors with `Unexpected token '<', "<!DOCTYPE"` because errand advertises the `cloud_storage` capability but does not implement the `/api/cloud-storage/*` REST surface the library calls — the request hits the SPA catch-all and returns `index.html`. Google Workspace and Jira have the same class of mismatch but are currently capability-gated off (latent).
3. `GET /api/plugins` returns 500 (`FileNotFoundError` on a missing installed-plugin dir) and marketplace resync raises `PluginInstallError`/`git clone failed`, surfacing as "Failed to fetch plugins: 500" and a marketplace "Sync error".

The library's `createDirectApi` calls `/api/cloud-storage/{status,authorize}`, `DELETE /api/cloud-storage`, `/api/google-workspace/{status,authorize}`, `DELETE /api/google-workspace`. errand-cloud's proxy forwards the same paths verbatim. errand already has the underlying machinery: OneDrive/cloud-storage token handling (`cloud_storage`, `errand/onedrive_routes.py`) and Google Workspace (`errand/google_routes.py`), plus a cloud OAuth flow (`/api/cloud/auth/*`). The gap is a thin REST surface at the library-expected paths returning the library's typed shapes.

## Goals / Non-Goals

**Goals:**
- Implement `/api/cloud-storage/*` and `/api/google-workspace/*` status/authorize/disconnect endpoints returning the library's typed shapes, wired to existing machinery, so both cards work on a standalone errand-server.
- Advertise the `cloud_storage` / `google_workspace` capabilities only when their backend surface is actually available, so a card never renders without a working endpoint.
- Make `GET /api/plugins` and marketplace resync degrade gracefully on missing/partial plugin state instead of 500ing.
- Bump `@errand-ai/ui-components` to the companion release (envelope unwrap, spacing, Jira path) and `VERSION`.

**Non-Goals:**
- The library-side envelope-unwrap, spacing, and Jira `direct.ts` path fix (companion change `fix-settings-cards-envelope-and-spacing`).
- errand-cloud's proxy Jira-path correction (its own repo).
- The intermittent shared-workspace `rclone rc 5572/config/update` 500 (transient; observation only).
- Reworking the errand-cloud SaaS connection endpoints (`/api/cloud/*`) — those are a different feature and stay as-is.

## Decisions

### Decision 1: New REST endpoints wrap existing machinery (not new features)
Add `/api/cloud-storage/*` and `/api/google-workspace/*` as thin FastAPI routes that adapt errand's existing cloud-storage (OneDrive) and Google Workspace token/OAuth machinery into the library's typed response shapes:
- `GET /api/cloud-storage/status` → `CloudStorageStatus` `{connected, provider?, account?, authorize_url?}`
- `POST /api/cloud-storage/authorize` → `CloudStorageAuthorizeResponse` `{authorize_url}`
- `DELETE /api/cloud-storage` → 204
- `GET /api/google-workspace/status` → `GoogleWorkspaceStatus`
- `POST /api/google-workspace/authorize` → authorize response
- `DELETE /api/google-workspace` → 204

**Why:** errand-cloud already forwards these exact paths; matching them (rather than aliasing existing `/api/cloud/*` or renaming in the library) keeps one contract across errand + errand-cloud and reuses the library's `direct.ts` unchanged for cloud/google. **Alternative rejected:** backend aliases of `/api/cloud/*` — those are the errand-cloud SaaS connection, semantically unrelated to cloud storage.

### Decision 2: Endpoints registered unconditionally; availability-aware capability gating
The `/api/cloud-storage/*` and `/api/google-workspace/*` **status** endpoints are registered unconditionally and always return JSON, so whenever a card is advertised its status call resolves to a real endpoint (never the SPA catch-all).

Capability gating is **availability-aware**: `get_capabilities()` advertises `cloud_storage` / `google_workspace` when the provider is actually connectable in the deployment — via local OAuth client credentials **or a connected errand-cloud OAuth proxy** (plus any required MCP URL, e.g. `ONEDRIVE_MCP_URL`) — or is already connected.

**Why:** the visible bug was a card rendering with no backend behind the status call (endpoint absent → SPA HTML → JSON parse crash); the unconditional endpoint removes that directly. The gating evolved during the change: an initial iteration kept plain env-var gates (`ONEDRIVE_MCP_URL`; `GOOGLE_CLIENT_ID`+`GOOGLE_CLIENT_SECRET`), but that hid the Google Workspace card on **cloud-connected deployments** (which use the OAuth proxy, not local client credentials) and offered a broken OneDrive "Connect". The availability-aware gate (`integration_routes._provider_available`, which considers local creds OR the cloud proxy) fixes both: the cards appear exactly when the provider can be connected. The capability tests were updated to match. See also Decision on cloud-preferred authorization in the accompanying config-tab fixes: when errand-cloud is connected, `_authorize_provider` uses the cloud OAuth proxy rather than local client id/secret.

### Decision 3: Plugin listing & marketplace sync degrade, never 500
- `GET /api/plugins`: when an installed-plugin directory or manifest is missing/unreadable, skip that plugin (or return it flagged) and log a warning — never raise to a 500.
- Marketplace sync/resync: install/clone failures for individual plugins are captured into `last_sync_status="error"` + `last_sync_error` (already the pattern for network/auth failures) rather than raising an uncaught `PluginInstallError`/`RuntimeError`.

**Why:** a single bad plugin (here, `anthropics/…/code-review` with a path the installer doesn't handle) currently takes down the whole listing and the whole resync. Graceful degradation keeps the rest of the UI functional and surfaces the specific failure.

## Risks / Trade-offs

- **[Response-shape drift]** errand's status endpoints might not perfectly match the library's TS types → the card renders but mis-binds. **Mitigation:** assert the shapes in backend tests against the library's documented types; verify live via Playwright on the local stack.
- **[Capability gating hides a working card]** Over-strict gating could hide a card that would actually work. **Mitigation:** gate on concrete signals (endpoint availability / configured provider), covered by tests for both on and off states.
- **[Plugin skip masks real corruption]** Silently skipping a broken plugin could hide a genuine install bug. **Mitigation:** always log a warning and surface a per-plugin/per-marketplace error indicator in the API response, not a silent drop.
- **[Library release ordering]** errand's dep bump requires the companion library release to be published first. **Mitigation:** sequence the merges; pin the exact new version in `frontend/package.json`.

## Migration Plan

1. Land + publish the companion library change (`fix-settings-cards-envelope-and-spacing`).
2. Implement backend endpoints + capability reconciliation + plugin/marketplace robustness in errand.
3. Bump `@errand-ai/ui-components` to the new version; `VERSION` bump.
4. Verify on the local docker-compose stack via Playwright: cards populate, Cloud storage shows a real status (not a JSON error), `/api/plugins` returns 200, marketplace resync reports errors inline.
5. Standard PR → CI → K8s validation per CLAUDE.md. Rollback = revert the dep bump + endpoints (additive, low blast radius).

## Open Questions

- Should `cloud_storage`/`google_workspace` authorize on a standalone server reuse the existing cloud OAuth proxy flow, or a direct provider OAuth? (Resolve in tasks against the existing `cloud_storage`/`google_routes` machinery.)
- Does the `code-review` plugin failure indicate a broader marketplace-manifest path assumption to fix, beyond graceful degradation? (Investigate during implementation; degradation is the floor, a manifest-path fix may be the ceiling.)
