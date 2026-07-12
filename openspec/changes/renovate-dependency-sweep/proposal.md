## Why

Nine Renovate pull requests have accumulated (oldest from mid-April 2026), including a `cryptography` **security** update. The PRs overlap heavily — five files are each touched by two-to-four PRs — so merging them individually triggers a rebase treadmill, and one PR (`#136`, mislabelled "non-major") smuggles a two-interpreter Python jump and ships a broken Dockerfile. Consolidating the sweep into one coordinated change lets us resolve the overlaps once, verify once, and land the security fix without waiting on the riskier migrations.

## What Changes

Address all nine open Renovate PRs, staged by risk into four implementation passes (detail and sequencing in `design.md`). Each pass is a separate branch/PR with its own `VERSION` bump; the corresponding Renovate PRs are closed as their content lands.

- **Pass 1 — Security + safe infra**: `cryptography` 46→48 (security, `#196`); `actions/checkout` v6→v7 (`#195`); Node 20/22→24 in CI and the task-runner (`#141`); `valkey` dev-compose image 8→9 (`#151`) plus aligning the Helm `valkey` chart dependency 0.9.x→0.10.x.
- **Pass 2 — Backend libraries**: `redis` client 7.4→8 (`#188`); `kubernetes` client 35→36 (`#185`); and the Python *library* patch/minor bumps carried by `#136` (fastapi, sqlalchemy, asyncpg, alembic, psycopg2, openai, docker, litellm image, test deps).
- **Pass 3 — Frontend majors**: Tailwind CSS 3→4 (`#167`); TypeScript 6→7 (`#197`); `@errand-ai/ui-components` 0.6→0.9 (carried by `#136`, prime suspect for the current vitest failures). **BREAKING** build-tooling migration (Tailwind v4 config format, new PostCSS plugin).
- **Pass 4 — Python interpreter 3.11/3.12 → 3.13**: errand image (fix the hard-coded `python3.12/site-packages` copy path), task-runner image (build stage **and** the distroless runtime base, which currently provides Python 3.11), and the CI Python version. Target is **3.13**, not `#136`'s literal 3.14, because no distroless base provides 3.14 and the task-runner's final stage is distroless by design (see design D6). This is the one genuinely broken piece of `#136`, done deliberately and last.
- **Dissolve `#136`**: its contents are correctly distributed across passes 2, 3, and 4 rather than merged as the half-broken bundle Renovate authored.

No product behaviour changes are intended; correctness is guarded by the existing test suites (errand pytest, task-runner pytest, frontend vitest) plus a local docker-compose smoke test for the runtime-affecting bumps.

## Capabilities

### New Capabilities
<!-- None — this is a dependency-maintenance sweep, not a feature. -->

### Modified Capabilities
- `task-runner-image`: the task-runner Dockerfile's pinned toolchain versions change — Node builder `node:22-bookworm-slim` → `node:24-bookworm-slim` (Pass 1), Python builder `python:3.11-slim` → `python:3.13-slim-trixie`, and the final distroless runtime base `gcr.io/distroless/python3-debian12` → `python3-debian13` (Python 3.11 → 3.13) (Pass 4). These interpreter/runtime versions are stated as requirements in the current spec, so bumping them is a spec-level delta.

## Impact

- **Dependencies**: `errand/requirements.txt`, `errand/requirements-test.txt`, `frontend/package.json` (+ lockfile), `helm/errand/Chart.yaml` + `Chart.lock`.
- **Build/CI**: `.github/workflows/build.yml`, `Dockerfile`, `errand/Dockerfile`, `task-runner/Dockerfile`, `deploy/docker-compose.yml` (and `testing/docker-compose.yml` if it carries the same tags).
- **Runtime surfaces to smoke-test**: Redis/Valkey pub-sub and caching (redis 8 / valkey 9), Kubernetes task execution (client 36), and the Python 3.13 interpreter across both images.
- **Frontend**: Tailwind v4 + TypeScript 7 migration affects the Vite build (`vue-tsc -b`) and all component styling; `@errand-ai/ui-components` 0.9 may require call-site adjustments.
- **Renovate PRs closed**: `#196`, `#195`, `#141`, `#151`, `#188`, `#185`, `#167`, `#197`, `#136`.
