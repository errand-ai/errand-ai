## Why

The project is being rebranded from "Content Manager" to "Errand". The domains `errand.so` and `errand.cloud` have been acquired for the public launch. All user-facing references, internal identifiers, and branding assets need to be updated to reflect the new name before release.

## What Changes

- Replace all user-visible "Content Manager" text with "Errand" (page title, header, README)
- Replace the logo image (`frontend/public/logo.png`) with the new Errand logo (`images/errand-logo-120.png`)
- Update internal identifiers that use `content-manager` where they are user-facing or appear in configuration (Keycloak client name in OIDC roles claim, MCP server name, Redis lock keys, Hindsight bank ID, SSH key comment, package.json name)
- Update Helm chart name, image repository references, and Kubernetes resource names
- Update CI/CD workflow references (image names, chart paths)
- Update docker-compose service references
- Update Serena project config and README

**Note**: The Keycloak client ID (`content-manager`) is an external dependency configured in Keycloak itself. The `resource_access` claim key in JWTs is controlled by Keycloak and cannot be changed by renaming code alone. This change will rename the Keycloak client configuration value (`OIDC_CLIENT_ID`, `OIDC_ROLES_CLAIM`) to reference `errand`, but the actual Keycloak client must also be renamed/recreated separately.

## Capabilities

### New Capabilities

(none)

### Modified Capabilities

- `helm-deployment`: Chart renamed from `content-manager` to `errand`, all template helper names updated, image repositories change to `ghcr.io/devops-consultants/errand-backend` and `errand-task-runner`
- `ci-pipelines`: Image names and chart path change from `content-manager` to `errand`
- `local-dev-environment`: docker-compose service names and image references updated
- `keycloak-auth`: OIDC client ID and roles claim path change from `content-manager` to `errand`
- `mcp-server-endpoint`: MCP server display name changes to "Errand"
- `frontend-auth`: Roles claim key changes from `content-manager` to `errand`
- `static-file-serving`: Logo asset replaced, page title updated

## Impact

- **Frontend**: App.vue header text + logo, index.html title, package.json name, auth store roles claim key, all test fixtures referencing `content-manager` in JWT payloads
- **Backend**: main.py SSH key comment, auth.py roles claim default, mcp_server.py name, worker.py image name + clone dir + bank ID + MCP injection key, scheduler.py Redis lock key, all backend tests
- **Helm chart**: Chart.yaml name, values.yaml image repos + secret names + roles claim, all template helpers and resource names
- **CI/CD**: build.yml image names and chart path
- **Config**: docker-compose.yml, .serena/project.yml, README.md
- **External**: Keycloak client must be renamed separately. ArgoCD app name and values file path will need manual update after deployment.
