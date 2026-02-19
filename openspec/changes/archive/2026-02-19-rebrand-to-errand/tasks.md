## 1. Frontend Branding

- [x] 1.1 Replace `frontend/public/logo.png` with `images/errand-logo-120.png`
- [x] 1.2 Update `frontend/index.html`: change `<title>Content Manager</title>` to `<title>Errand</title>`
- [x] 1.3 Update `frontend/src/App.vue`: change header text from "Content Manager" to "Errand"
- [x] 1.4 Update `frontend/package.json`: change `name` from `content-manager-frontend` to `errand-frontend`

## 2. Frontend Auth — Keycloak Client Key

- [x] 2.1 Update `frontend/src/stores/auth.ts`: change `resource_access?.['content-manager']` to `resource_access?.['errand']`
- [x] 2.2 Update `frontend/src/components/settings/McpApiKeySettings.vue`: change `content-manager` MCP server key to `errand`

## 3. Frontend Tests

- [x] 3.1 Update all JWT fixture `resource_access` keys from `content-manager` to `errand` in: `AppNavigation.test.ts`, `AppHeader.test.ts`, `auth.test.ts`, `auth-rbac.test.ts`, `KanbanBoardRbac.test.ts`, `SettingsPage.test.ts`
- [x] 3.2 Update MCP config assertions in `SettingsPage.test.ts` from `content-manager` to `errand`
- [x] 3.3 Run frontend tests and verify all pass

## 4. Backend — Identity and Naming

- [x] 4.1 Update `backend/mcp_server.py`: change MCP server name from "Content Manager" to "Errand"
- [x] 4.2 Update `backend/main.py`: change SSH key comment from `content-manager` to `errand`
- [x] 4.3 Update `backend/main.py`: change `resource_access` key from `content-manager` to `errand` in roles extraction
- [x] 4.4 Update `backend/auth.py`: change default `OIDC_ROLES_CLAIM` from `resource_access.content-manager.roles` to `resource_access.errand.roles`
- [x] 4.5 Update `backend/scheduler.py`: change Redis lock key from `content-manager:scheduler-lock` to `errand:scheduler-lock`
- [x] 4.6 Update `backend/worker.py`: change `TASK_RUNNER_IMAGE` default from `content-manager-task-runner:latest` to `errand-task-runner:latest`
- [x] 4.7 Update `backend/worker.py`: change clone dir prefix from `content-manager-skills` to `errand-skills`
- [x] 4.8 Update `backend/worker.py`: change `DEFAULT_HINDSIGHT_BANK_ID` from `content-manager-tasks` to `errand-tasks`
- [x] 4.9 Update `backend/worker.py`: change MCP injection key from `content-manager` to `errand`

## 5. Backend Tests

- [x] 5.1 Update all JWT fixture `resource_access` keys from `content-manager` to `errand` in: `conftest.py`, `test_websocket.py`, `test_mcp.py`, `test_task_audit.py`
- [x] 5.2 Update `test_settings.py`: change SSH key comment assertion from `content-manager` to `errand`
- [x] 5.3 Update `test_worker.py`: change MCP injection key assertions from `content-manager` to `errand`, clone dir assertions, and Hindsight bank ID assertion
- [x] 5.4 Run backend tests and verify all pass

## 6. Helm Chart

- [x] 6.1 Rename `helm/content-manager/` directory to `helm/errand/`
- [x] 6.2 Update `helm/errand/Chart.yaml`: change `name` from `content-manager` to `errand`
- [x] 6.3 Update `helm/errand/templates/_helpers.tpl`: rename helpers from `content-manager.*` to `errand.*`
- [x] 6.4 Update all templates to use `errand.fullname` and `errand.labels` (backend-deployment, worker-deployment, backend-service, perplexity-service, perplexity-deployment, ingress, migration-job, keda-scaledobject)
- [x] 6.5 Update `helm/errand/values.yaml`: change image repositories to `ghcr.io/devops-consultants/errand-backend` and `errand-task-runner`, update roles claim to `resource_access.errand.roles`, update Hindsight bank ID to `errand-tasks`

## 7. CI/CD

- [x] 7.1 Update `.github/workflows/build.yml`: change Helm chart path from `helm/content-manager` to `helm/errand`
- [x] 7.2 Update `.github/workflows/build.yml`: change image name references from `content-manager-backend` to `errand-backend` and `content-manager-task-runner` to `errand-task-runner`

## 8. Docker Compose and Config

- [x] 8.1 Update `docker-compose.yml`: change `TASK_RUNNER_IMAGE` to `errand-task-runner:latest`, `OIDC_ROLES_CLAIM` to `resource_access.errand.roles`, and task-runner build tag to `errand-task-runner:latest`
- [x] 8.2 Update `.serena/project.yml`: change project name from `content-manager` to `errand`
- [x] 8.3 Update `README.md`: replace "Content Manager" with "Errand" and `content-manager` references where appropriate

## 9. Final Verification

- [x] 9.1 Run full frontend test suite
- [x] 9.2 Run full backend test suite
- [x] 9.3 Grep codebase for remaining `content-manager` references (excluding openspec archives, .git, node_modules) and address any missed occurrences
