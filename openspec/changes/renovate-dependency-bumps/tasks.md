## 1. Feature branch and versioning

- [x] 1.1 Create a feature branch `renovate-dependency-bumps` off `main`
- [x] 1.2 Bump the `VERSION` file with a minor-level increment (new dependency majors warrant minor)

## 2. Backend dependency bumps (requirements.txt)

- [x] 2.1 Update `cryptography==46.0.6` → `cryptography==46.0.7`
- [x] 2.2 Update `fastapi==0.115.0` → `fastapi==0.136.0`
- [x] 2.3 Update `sqlalchemy[asyncio]==2.0.35` → `sqlalchemy[asyncio]==2.0.49`
- [x] 2.4 Update `alembic==1.13.3` → `alembic==1.18.4`
- [x] 2.5 Update `asyncpg==0.29.0` → `asyncpg==0.31.0`
- [x] 2.6 Update `httpx==0.27.2` → `httpx==0.28.1`
- [x] 2.7 Update `psycopg2-binary==2.9.9` → `psycopg2-binary==2.9.11`
- [x] 2.8 Update `redis[hiredis]==5.2.1` → `redis[hiredis]==7.4.0`
- [x] 2.9 Update `openai==1.82.0` → `openai==2.32.0`
- [x] 2.10 Change `bcrypt>=4.0.0,<5.0.0` → `bcrypt>=5.0.0`
- [x] 2.11 Update `marked` dependency: this is a frontend dep, skip here (handled in section 4)

## 3. Backend test dependency bumps (requirements-test.txt)

- [x] 3.1 Update `pytest==8.4.2` → `pytest==9.0.3`
- [x] 3.2 Update `pytest-asyncio==0.24.0` → `pytest-asyncio==1.3.0`
- [x] 3.3 Update `aiosqlite==0.20.0` → `aiosqlite==0.22.1`
- [x] 3.4 Update `fakeredis==2.26.2` → `fakeredis==2.35.1`
- [x] 3.5 Recreate the venv: `/opt/homebrew/bin/python3.12 -m venv errand/.venv && errand/.venv/bin/pip install -r errand/requirements.txt -r errand/requirements-test.txt`
- [x] 3.6 If pytest-asyncio 1.x changes default mode, add `asyncio_mode = "auto"` to pytest config (already configured in pytest.ini)
- [x] 3.7 Run backend tests: `DATABASE_URL="sqlite+aiosqlite:///:memory:" errand/.venv/bin/python -m pytest errand/tests/ -v`. All 1381 tests passed. (bcrypt v5 required replacing passlib with direct bcrypt usage)

## 4. Frontend dependency bumps (package.json)

- [x] 4.1 Update `marked` from `^17.0.2` → `^18.0.0`
- [x] 4.2 Update `pinia` from `^2.2.0` → `^3.0.0`
- [x] 4.3 Update `vue-router` from `^4.6.4` → `^5.0.0`
- [x] 4.4 Update `vite` from `^5.4.21` → `^7.0.0`
- [x] 4.5 Update `@vitejs/plugin-vue` from `^5.1.0` → `^6.0.0`
- [x] 4.6 Update `typescript` from `~5.6.0` → `~6.0.0`
- [x] 4.7 Update `vue-tsc` from `^2.1.0` → `^3.0.0`
- [x] 4.8 Update `jsdom` from `^28.0.0` → `^29.0.0`
- [x] 4.9 Apply non-major bumps from Renovate #136: vue patch, vitest minor, postcss patch, autoprefixer minor, @types/dompurify minor
- [x] 4.10 Run `cd frontend && npm install` to regenerate `package-lock.json` (+ npm audit fix --legacy-peer-deps for transitive vulns)
- [x] 4.11 Run `cd frontend && npm run test`. All 337 frontend tests passed.
- [x] 4.12 Run `cd frontend && npm run build`. Production build completed successfully.
- [x] 4.13 Run `cd frontend && npx vue-tsc --noEmit`. TypeScript type-checking passed with TS 6.

## 5. Docker infrastructure updates

- [x] 5.1 Update Dockerfile: change `FROM node:20-alpine` → `FROM node:24-alpine` in the frontend-build stage
- [x] 5.2 Update `testing/docker-compose.yml`: change `postgres:16-alpine` → `postgres:18-alpine`
- [x] 5.3 Update `testing/docker-compose.yml`: change `valkey/valkey:8-alpine` → `valkey/valkey:9-alpine`

## 6. Local end-to-end smoke test

- [x] 6.1 Run `docker compose -f testing/docker-compose.yml up --build` from repo root; errand-server healthy. Fixed: asyncpg pinned to 0.30.0 (0.31.0 lacks manylinux wheel), added legacy-peer-deps=true to .npmrc for ui-components peer dep conflict.
- [x] 6.2 Playwright UI test: login succeeded (bcrypt migration works), kanban board renders with all columns, task creation works, edit modal works (pinia 3 + vue-router 5), settings pages render (security page confirms cryptography bump), zero console errors.
- [x] 6.3 `docker compose -f testing/docker-compose.yml down`

## 7. PR and review

- [ ] 7.1 Commit on the feature branch, push to origin, open a PR against `main`
- [ ] 7.2 Confirm CI passes (tests, Docker build, Helm chart package)
- [ ] 7.3 Verify the PR-tagged deployment on Kubernetes before merging (per CLAUDE.md Development Workflow step 5)
- [ ] 7.4 Merge to `main`

## 8. Post-merge: Renovate PR cleanup

- [ ] 8.1 For each of the 18 Renovate PRs (#124–#151), tick the "rebase/retry" checkbox to trigger Renovate to re-evaluate against the updated lockfiles
- [ ] 8.2 Verify that PRs for dependencies we bumped are auto-closed by Renovate
- [ ] 8.3 Confirm #146 (tailwindcss v4) remains open (intentionally deferred)
