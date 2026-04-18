## Why

Renovate has opened 18 dependency update PRs against this repository. Most are major version bumps that have accumulated while Dependabot was the primary dependency manager. Addressing them in a single coordinated change reduces CI churn, avoids version conflicts between interdependent packages (especially the Vue ecosystem), and closes security advisories (vite CVE-2026-39364, pytest CVE, cryptography patch).

Tailwind CSS v4 and the Python 3.12→3.14 base image bump are excluded — Tailwind v4 is a major rewrite requiring a two-repo migration (ui-components depends on v3), and the Python base image is a separate concern.

## What Changes

### Backend (Python)
- `cryptography` 46.0.6 → 46.0.7 (patch, security)
- `pytest` 8.x → 9.x (major, security, test-only)
- `pytest-asyncio` 0.24 → 1.x (major, test-only)
- `openai` 1.x → 2.x (major — usage is vanilla AsyncOpenAI, API-compatible)
- `redis` 5.x → 7.x (major — standard API usage, transparent upgrade)
- `bcrypt` `>=4.0.0,<5.0.0` → `>=5.0.0` (major)
- `marked` 17 → 18 (major, frontend runtime dep)
- Non-major bumps from Renovate #136: fastapi, sqlalchemy, alembic, asyncpg, httpx, psycopg2-binary, aiosqlite, fakeredis, redis minor, openai minor, pytest-asyncio minor

### Frontend (JavaScript/TypeScript)
- `vite` 5.x → 7.x (major, security CVE-2026-39364)
- `@vitejs/plugin-vue` 5 → 6 (major, pairs with vite 7)
- `typescript` ~5.6 → 6.x (major, type-checking only)
- `vue-tsc` 2 → 3 (major, pairs with TS 6)
- `vue-router` 4 → 5 (major — already uses modern guard API)
- `pinia` 2 → 3 (major — drops Vue 2 only, no API changes for our usage)
- `jsdom` 28 → 29 (major, test-only)
- Non-major bumps from Renovate #136: vue patch, vitest minor, postcss patch, autoprefixer minor, @types/dompurify minor, typescript 5.6→5.9

### Docker (compose + Dockerfile)
- `node` 20 → 24 (Dockerfile build stage, LTS)
- `postgres` 16 → 18 (docker-compose local dev only)
- `valkey` 8 → 9 (docker-compose local dev only)

## Capabilities

### New Capabilities

None — this is a dependency-only change.

### Modified Capabilities

- `ci-pipelines`: Node.js build stage version changes from 20 to 24
- `local-dev-environment`: PostgreSQL 16→18 and Valkey 8→9 in docker-compose
- `backend-tests`: pytest 8→9 and pytest-asyncio 0.24→1.x may require test configuration changes
- `frontend-tests`: jsdom 28→29, vitest minor bump

## Impact

- **errand/requirements.txt**: Multiple version bumps, bcrypt cap removal
- **errand/requirements-test.txt**: pytest and pytest-asyncio major bumps
- **frontend/package.json**: Vue ecosystem cascade (vite, plugin-vue, TS, vue-tsc, vue-router, pinia) plus minor bumps
- **frontend/package-lock.json**: Full regeneration
- **Dockerfile**: Node 20→24 base image
- **testing/docker-compose.yml**: postgres 16→18, valkey 8→9
- **All backend tests and frontend tests** must pass after bumps
- **Renovate PRs**: After merging, trigger rebase/retry on all 18 PRs to auto-close resolved ones
