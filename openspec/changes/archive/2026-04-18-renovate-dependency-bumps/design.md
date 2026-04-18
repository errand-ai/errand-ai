## Context

The project has 18 open Renovate PRs covering dependency updates across Python backend, Vue frontend, and Docker infrastructure. Dependencies have drifted significantly — some are 2+ major versions behind. The Vue ecosystem packages (vite, vue-router, pinia, TypeScript, vue-tsc, @vitejs/plugin-vue) are interrelated and must be upgraded together.

The previous `fix-dependabot-alerts` change handled security-critical bumps (cryptography, python-multipart, pytest patch, vite patch, tailwind patch, ui-components). This change takes the next step: absorbing all remaining Renovate PRs except Tailwind v4 and Python 3.14.

## Goals / Non-Goals

**Goals:**
- Bump all backend Python dependencies to their latest major/minor versions
- Upgrade the full Vue frontend toolchain (vite 7, TS 6, vue-router 5, pinia 3)
- Update Docker infrastructure images (node 24, postgres 18, valkey 9)
- Ensure all 839 backend tests and 440 frontend tests pass
- Enable Renovate PR auto-closure via rebase/retry after merge

**Non-Goals:**
- Tailwind CSS v3 → v4 migration (requires ui-components upgrade first)
- Python 3.12 → 3.14 base image upgrade (separate concern)
- Any feature work or refactoring beyond what the version bumps require

## Decisions

### Backend upgrades are applied directly to pinned versions

**Decision**: Edit `requirements.txt` and `requirements-test.txt` directly, changing pinned versions. Do not switch to range specifiers.

**Rationale**: The project pins exact versions (`==`) for reproducible builds. Renovate manages version discovery — we just need to accept the bumps. The `bcrypt` entry is the exception: remove the `<5.0.0` upper cap to allow v5.

### Vue ecosystem packages upgrade as a single atomic batch

**Decision**: Upgrade vite, @vitejs/plugin-vue, typescript, vue-tsc, vue-router, and pinia together in one step rather than sequentially.

**Rationale**: These packages have peer dependency relationships. Vite 7 requires plugin-vue 6. TypeScript 6 requires vue-tsc 3. Upgrading them individually would create transient incompatibilities. A single `npm install` after updating all versions in package.json resolves everything cleanly.

### Non-major bumps from Renovate #136 are absorbed into this change

**Decision**: Cherry-pick the safe non-major bumps from #136 (fastapi, sqlalchemy, httpx, vue, vitest, etc.) but skip the Python 3.12→3.14 Docker base image change and the litellm compose image bump.

**Rationale**: The non-major bumps are low-risk and reduce the number of PRs to manage. The Python version and litellm bumps are unrelated infrastructure changes that are better handled separately.

### openai v1 → v2: no code changes expected

**Decision**: Bump openai from 1.x to 2.x without code changes.

**Rationale**: The project uses only `AsyncOpenAI(base_url=..., api_key=...)` instantiation and standard `client.chat.completions.create()` / `client.models.list()` calls. The openai v2 SDK maintains backwards compatibility for these core patterns. The breaking changes are around new response types, agents API, and websocket features — none of which this project uses. Tests will validate.

### redis 5 → 7: no code changes expected

**Decision**: Bump redis from 5.x to 7.x without code changes.

**Rationale**: The project uses `Redis.from_url()`, `redis.asyncio.Redis`, `.set()`, `.close()` — all standard API. The v6/v7 changes focus on RESP3 protocol support, cluster improvements, and observability features. The basic client API is unchanged.

### pytest-asyncio 0.24 → 1.x: check for mode changes

**Decision**: Bump pytest-asyncio to 1.x. If the default mode changed, add `asyncio_mode = "auto"` to `pyproject.toml` or `pytest.ini` if tests fail.

**Rationale**: pytest-asyncio 1.x may change the default mode from `auto` to `strict`. The project's tests likely rely on auto mode. If tests fail with "no event loop", the fix is a one-line config addition.

### Node 20 → 24 in Dockerfile only

**Decision**: Update the `FROM node:20-alpine` line in the Dockerfile to `node:24-alpine`. Do not change CI matrix or local development Node version.

**Rationale**: Node 24 is the current LTS. The Dockerfile only uses Node for the frontend build stage (`npm install && npm run build`). No Node.js runtime features are used — it's purely a build tool. Node 20 reached end-of-life in April 2026.

## Risks / Trade-offs

**TypeScript 6 may surface new type errors** → Run `vue-tsc --noEmit` and fix any new errors. These are typically stricter null checks or narrowing changes, not runtime bugs.

**pytest 9 may deprecate fixtures or change defaults** → Test suite is large (839 tests) and will surface any issues immediately. Pytest major bumps are historically low-friction.

**marked 17 → 18 may change rendering** → marked is used for task output rendering. Verify markdown output visually during smoke test.

**httpx 0.27 → 0.28 minor bump** → httpx 0.28 changed some default behaviors around redirects. The project uses httpx primarily in tests via `AsyncClient`. Should be transparent but tests will catch any issues.

**Multiple major bumps in one PR increases blast radius** → Mitigated by the fact that all 839+440 tests must pass, plus a full docker-compose smoke test. If a specific bump causes issues, it can be isolated and reverted within the branch before merging.
