## 1. Preflight investigation

- [x] 1.1 Bisect the frontend vitest failure: on throwaway branches apply each of TypeScript 7 (`#197`), Tailwind 4 (`#167`), and `@errand-ai/ui-components` 0.9 (from `#136`) **alone** against `npm run test` + `vue-tsc -b`; record which one(s) break and why (informs Pass 3 shape/split)
- [x] 1.2 Check PyPI for `cp314` wheels (linux amd64 + arm64) for every compiled backend dep (`psycopg2-binary`, `asyncpg`, `redis[hiredis]`, `cryptography`); note any that would fall back to source builds or must be held (informs Pass 4)
- [x] 1.3 Determine whether a distroless base providing Python 3.14 exists (e.g. `gcr.io/distroless/python3-debian13:nonroot`); if not, decide the task-runner runtime fallback and record it in `design.md` Open Questions (informs Pass 4)
- [x] 1.4 Check `testing/docker-compose.yml` (distinct from `deploy/docker-compose.yml`) for valkey/other image tags that also need bumping in Pass 1

## 2. Pass 1 — Security + safe infra (branch `deps-pass-1-security-infra`, VERSION patch bump)

- [x] 2.1 Create branch from latest `main` and bump `VERSION` (patch)
- [x] 2.2 Bump `cryptography` 46.0.7 → 48.0.1 in `errand/requirements.txt` (`#196`, security)
- [x] 2.3 Bump `actions/checkout` v6 → v7 in `.github/workflows/build.yml` (`#195`)
- [x] 2.4 Bump Node 20/22 → 24: `setup-node` in `.github/workflows/build.yml` and the `node-builder` stage in `task-runner/Dockerfile` (`#141`)
- [x] 2.5 Bump `valkey/valkey` image 8 → 9-alpine in `deploy/docker-compose.yml` (and `testing/docker-compose.yml` if 1.4 found it), and align the Helm `valkey` chart dependency 0.9.x → 0.10.x in `helm/errand/Chart.yaml` + regenerate `Chart.lock` (`#151` + `#136`'s chart bump)
- [x] 2.6 Verify: errand pytest + task-runner pytest + frontend vitest all green; `docker compose up --build` starts cleanly (valkey 9 healthy)
- [x] 2.7 Open PR, confirm CI green + Helm chart packages, validate Helm deploy (dry-run/ArgoCD), merge, then close Renovate PRs `#196`, `#195`, `#141`, `#151`

## 3. Pass 2 — Backend libraries (branch `deps-pass-2-backend-libs`, VERSION minor bump)

- [x] 3.1 Create branch from latest `main` and bump `VERSION` (minor)
- [x] 3.2 Bump `redis[hiredis]` 7.4.0 → 8.0.1 (`#188`); review redis-py 8 changelog for connection/API breaking changes affecting pub-sub usage
- [x] 3.3 Bump `kubernetes` client `>=28.0.0,<36` → `>=36.0.2,<37` (`#185`); review k8s client 36 changelog for model/enum changes touching `k8s-task-execution`
- [x] 3.4 Apply `#136`'s Python library patch/minor bumps in `errand/requirements.txt` (fastapi 0.139, sqlalchemy 2.0.51, asyncpg 0.31, alembic 1.18.5, psycopg2-binary 2.9.12, openai 2.45, docker 7.2) — **excluding** the redis 7.4.1 and `kubernetes <36` re-pins (superseded by 3.2/3.3)
- [x] 3.5 Apply `#136`'s test-dependency bumps in `errand/requirements-test.txt` (pytest 9.1.1, pytest-asyncio 1.4.0, fakeredis 2.36.2) and the litellm image bump in `deploy/docker-compose.yml`
- [x] 3.6 Verify: errand pytest + task-runner pytest green; `docker compose up --build` smoke test — dispatch a task through the runner and confirm redis/valkey pub-sub + k8s/docker runtime paths work
- [ ] 3.7 Open PR, confirm CI green + images build, validate on K8s, merge, then close Renovate PRs `#188`, `#185` (and mark their content in `#136` as landed)

## 4. Pass 3 — Frontend majors (branch `deps-pass-3-frontend-majors`, VERSION minor bump)

- [x] 4.1 Create branch from latest `main` and bump `VERSION` (minor)
- [x] 4.2 Migrate Tailwind CSS 3 → 4 (`#167`): ran `@tailwindcss/upgrade` — `@tailwindcss/postcss` plugin, `@import "tailwindcss"` + `@plugin`/`@source` in `main.css`, deleted `tailwind.config.js`, autoprefixer removed, ~30 templates renamed (appearance-preserving: `rounded`→`rounded-sm`, `shadow`→`shadow-sm`, `shadow-sm`→`shadow-xs`, `outline-none`→`outline-hidden`)
- [~] 4.3 **DEFERRED — TypeScript 6 → 7 (`#197`)**: TS 7 is the native (Go) compiler; its package drops `typescript/lib/tsc`, which `vue-tsc` (all released versions, incl. 3.3.7) still resolves → `vue-tsc -b` crashes, breaking the build's type-check. No `vue-tsc` supports the native compiler yet. Kept at `~6.0.0`; `#197` stays open pending Vue tooling support (see design D7).
- [x] 4.4 Bump `@errand-ai/ui-components` 0.6 → 0.9 (from `#136`) — no call-site changes needed; validated in isolation (vue-tsc 0 errors, vitest 389 passed)
- [x] 4.5 Verify: vitest **389 passed** + `npm run build` (vue-tsc + vite) exit 0 (v4 CSS compiles). Live visual QA of authenticated screens (kanban, task form, settings) deferred to the PR deployment — the SPA is auth-gated and can't render meaningfully without the backend
- [ ] 4.6 Open PR, confirm CI green + frontend static assets build into the image, merge, then close Renovate PR `#167` (`#197` remains open — deferred per 4.3)

## 5. Pass 4 — Python interpreter 3.11/3.12 → 3.13 (branch `deps-pass-4-python-313`, VERSION minor bump)

<!-- Target is 3.13 (keep distroless), per design D6 — no distroless base offers 3.14. -->

- [ ] 5.1 Create branch from latest `main` and bump `VERSION` (minor)
- [ ] 5.2 `errand/Dockerfile`: bump base `python:3.12` → `python:3.13` **and** correct the hard-coded `COPY .../python3.12/site-packages` path so it matches the new interpreter (`python3.13`)
- [ ] 5.3 `Dockerfile` (root, multi-stage): bump the wheel-download and runtime stages `python:3.12`/`3.12-slim` → 3.13, and fix any hard-coded `python3.12` site-packages copy path
- [ ] 5.4 `task-runner/Dockerfile`: bump the python builder `python:3.11-slim` → `python:3.13-slim-trixie` and the final distroless runtime `gcr.io/distroless/python3-debian12` → `python3-debian13` (Python 3.13), keeping build/runtime on the same Debian release (trixie) for ABI compatibility
- [ ] 5.5 Bump CI `python-version` '3.12' → '3.13' in `.github/workflows/build.yml`
- [ ] 5.6 Verify: full `docker build` of both errand and task-runner images succeeds on amd64 + arm64; `python3 --version` in the task-runner image reports 3.13.x; errand + task-runner pytest green; `docker compose up --build` smoke test passes
- [ ] 5.7 Open PR, confirm CI green + both images build + push, validate on K8s, merge, then close Renovate PR `#136` (final piece)

## 6. Close-out

- [ ] 6.1 Confirm the eight addressed Renovate PRs (`#136`, `#141`, `#151`, `#167`, `#185`, `#188`, `#195`, `#196`) are closed. `#197` (TypeScript 7) intentionally remains open — deferred per design D7
- [ ] 6.2 Run `/opsx:sync` to sync the `task-runner-image` delta into `openspec/specs/`, reconciling final base-image names with what actually shipped (per Pass 4 outcome)
- [ ] 6.3 Run `/opsx:archive` to archive the change
