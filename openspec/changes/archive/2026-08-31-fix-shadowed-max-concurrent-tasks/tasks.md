## 1. Remove the chart default

- [x] 1.1 Delete `server.maxConcurrentTasks: 3` from `helm/errand/values.yaml`
- [x] 1.2 Confirm `helm/errand/templates/server-deployment.yaml` still guards the env var with `{{- if .Values.server.maxConcurrentTasks }}` and emits nothing when unset
- [x] 1.3 Document the value in the chart README / values comments as an optional operator override that makes the setting readonly in the UI
- [x] 1.4 Verify no values file in `~/github/argocd` (`errand-rancher`, `errand-cloud`, `errand-sh`) sets `server.maxConcurrentTasks`; if any does, decide with the operator whether to keep the pin
- [x] 1.5 Remove the other `values.yaml` defaults that shadow registry keys — `keycloak.discoveryUrl`, `keycloak.rolesClaim`, `hindsight.bankId` — as required by the `Helm values defaults` requirement
- [x] 1.6 Guard `OIDC_DISCOVERY_URL` / `OIDC_ROLES_CLAIM` with `{{- if }}` (they were emitted unconditionally, so blanking the values alone would emit an empty env var)
- [x] 1.7 Pin `keycloak.discoveryUrl` in `~/github/argocd/errand-rancher-values.yaml` so the live deployment's auth wiring is unchanged (`OIDCConfig.from_env` needs it alongside the client id/secret, or OIDC silently deactivates)

## 2. Make the refusal observable in the API

- [x] 2.1 In `errand/main.py` `update_settings`, log a WARNING when a key is skipped for being env-sourced, naming both the setting key and `meta["env_var"]`
- [x] 2.2 Confirm the response still returns `resolve_settings(session)` unchanged in shape, with refused keys carrying `source: "env"` and `readonly: true`
- [x] 2.3 Confirm editable keys sent in the same request body are still persisted (no early return / no exception path)

## 3. Tests

- [x] 3.1 Chart test: rendering with default values emits no `MAX_CONCURRENT_TASKS` env var on the server Deployment
- [x] 3.2 Chart test: `server.maxConcurrentTasks: 5` still emits `MAX_CONCURRENT_TASKS=5`
- [x] 3.3 API test: PUT of an env-shadowed key does not write a `settings` row and returns that key as `readonly: true`, `source: "env"`
- [x] 3.4 API test: a request mixing an editable key and an env-shadowed key returns 200, persists the editable key, and refuses the other
- [x] 3.5 API test: the WARNING is emitted once per refused key (assert via `caplog`)
- [x] 3.6 Run the errand suite: `DATABASE_URL="sqlite+aiosqlite:///:memory:" errand/.venv/bin/python -m pytest errand/tests/ -q`
- [x] 3.7 Chart test: no registry-backed env var is emitted from a `values.yaml` default (the general form of the requirement, not just `MAX_CONCURRENT_TASKS`)
- [x] 3.8 API test: `max_concurrent_tasks` reports `readonly: false` and is writable when the env var is unset

## 4. Verify end to end

- [x] 4.1 Bump `VERSION` (patch)
- [x] 4.2 `docker compose -f testing/docker-compose.yml up --build` — compose sets no `MAX_CONCURRENT_TASKS`, so confirm the field saves and persists across a page reload
- [x] 4.3 Push, open PR, confirm CI builds images + chart
- [x] 4.4 Deploy the PR build to Kubernetes and confirm `GET /api/settings` reports `max_concurrent_tasks` with `source: "database"` (or `"default"`) and `readonly: false`
- [x] 4.5 Change the value in the UI and confirm the task manager picks it up on the next poll cycle without a restart (look for `Updating max_concurrent_tasks: 3 -> N (source=database)` in the server log)

## 5. Archive

- [x] 5.1 `openspec archive fix-shadowed-max-concurrent-tasks -y` and commit the flattened specs in this PR

## Post-merge notes

- No post-archive re-verification was needed. `build.yml` carries
  `paths-ignore: openspec/**`, so an archive commit touching only `openspec/`
  produces no new image tag and the build verified in 4.4/4.5
  (`0.147.0-pr251.1178`) remains the deployed artifact. Re-verify only if the
  archive commit is amended to touch code as well.
- **Commit and push `~/github/argocd/errand-rancher-values.yaml` before the new
  chart reaches the cluster.** Ordering is safe in either direction on the old
  chart (which reads the same key unconditionally, so an explicit value simply
  restates the default), but the new chart emits no `OIDC_DISCOVERY_URL` without
  it and Keycloak login would stop working.
- `errand-cloud-values.yaml` / `errand-sh-values.yaml` carry no `keycloak:`
  block. Confirm neither deployment relies on the removed chart default for OIDC
  before rolling the new chart out to them.
- Merge the PR once the post-archive build is verified.
- The settings card still renders an editable input for keys the API reports as
  `readonly: true`. That is tracked as `surface-readonly-settings` in
  `errand-ai/errand-component-library`; it consumes the response contract locked
  by section 2 and needs a `@errand-ai/ui-components` release plus a version bump
  in `frontend/package.json` here.
