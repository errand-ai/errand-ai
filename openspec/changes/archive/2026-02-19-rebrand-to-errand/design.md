## Context

The project is rebranding from "Content Manager" to "Errand". This is a naming/branding change across the full stack — no logic changes, no new features. The scope is find-and-replace of identifiers and assets, with care taken around external dependencies (Keycloak, ArgoCD, Kubernetes secrets).

## Goals / Non-Goals

**Goals:**
- Replace all user-visible "Content Manager" references with "Errand"
- Replace the logo with the new Errand logo
- Update internal identifiers (package names, image names, Helm chart name, Redis keys, etc.)
- Keep all tests passing with updated assertions
- Maintain backward compatibility with existing Keycloak configuration during transition

**Non-Goals:**
- Renaming the GitHub repository (stays `content-manager` for now)
- Renaming the git branch or local directory structure
- Changing the Keycloak client in Keycloak itself (separate ops task)
- Renaming ArgoCD app or its values file path (done post-deploy)
- Renaming Kubernetes secrets (done separately in cluster)
- Renaming the openspec directory structure or archived changes
- Updating the CLAUDE.md project instructions (done after merge)

## Decisions

### 1. Keycloak client ID: make configurable, default to `errand`

The `resource_access` key in JWTs is determined by the Keycloak client ID. Currently hardcoded as `content-manager` in:
- `backend/auth.py` (roles claim default)
- `frontend/src/stores/auth.ts` (hardcoded key)
- `backend/worker.py` (MCP injection)

**Decision**: Change the default from `content-manager` to `errand` in code. The Helm values already parameterize the roles claim via `OIDC_ROLES_CLAIM`. The frontend auth store key will be changed to `errand`. The Keycloak client itself must be renamed separately — during transition, update the Helm values to point to whichever client ID is active.

### 2. Docker image names: rename to `errand-backend` and `errand-task-runner`

CI builds and pushes images as `ghcr.io/devops-consultants/content-manager-backend` and `content-manager-task-runner`. These change to `errand-backend` and `errand-task-runner`. Old images remain in GHCR but are not cleaned up as part of this change.

### 3. Helm chart: rename to `errand`

Chart.yaml `name` changes to `errand`. All template helpers change from `content-manager.*` to `errand.*`. The chart directory stays at `helm/content-manager/` for now (will be renamed in a follow-up if desired, since the directory name is referenced in CI and ArgoCD).

**Update**: Actually, rename the chart directory from `helm/content-manager/` to `helm/errand/` in this change. The CI workflow and ArgoCD values path reference it, so those must be updated together.

### 4. Logo replacement

Copy `images/errand-logo-120.png` to `frontend/public/logo.png`, replacing the existing file. The `<img>` tag in App.vue already references `/logo.png` so no template change is needed beyond the file swap.

### 5. Redis lock key and Hindsight bank ID

Change `content-manager:scheduler-lock` to `errand:scheduler-lock` and `content-manager-tasks` to `errand-tasks`. These are internal identifiers with no persistence concern (Redis locks are ephemeral, Hindsight bank can be re-created).

### 6. SSH key comment

The SSH key comment in `main.py` changes from `content-manager` to `errand`. This is cosmetic and only affects newly generated keys.

## Risks / Trade-offs

- **Keycloak transition**: Until the Keycloak client is renamed, the deployed app must override `OIDC_CLIENT_ID` and `OIDC_ROLES_CLAIM` in Helm values to match the existing Keycloak client name. After Keycloak is updated, remove the overrides.
- **ArgoCD**: The ArgoCD app name (`content-manager`) and values file (`content-manager-rancher-values.yaml`) are external to this repo. They must be updated separately after this change is deployed.
- **Kubernetes secrets**: Secret names in the cluster (`content-manager-db`, `content-manager-keycloak`) are referenced in Helm values. These must be renamed in the cluster or the values overridden.
- **GHCR image history**: Old image tags under `content-manager-*` names won't be cleaned up automatically.
