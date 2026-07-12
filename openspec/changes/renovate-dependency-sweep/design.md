## Context

Nine open Renovate PRs (`#136`, `#141`, `#151`, `#167`, `#185`, `#188`, `#195`, `#196`, `#197`) span backend Python libraries, the frontend toolchain, CI actions, Docker base images, and the Helm chart. They are **not independent**: `errand/requirements.txt` (4 PRs), `frontend/package.json` (3), `.github/workflows/build.yml` (3), `deploy/docker-compose.yml` (2), and `task-runner/Dockerfile` (2) are each touched by multiple PRs. Merging any one invalidates the others' branches and forces a Renovate rebase.

Current CI state:
- **Clean**: `#196` (crypto, security), `#195` (checkout v7), `#188` (redis 8), `#185` (k8s 36), `#141` (node 24). `#151` (valkey compose) is trivial, mergeability pending recompute.
- **Failing tests**: `#197` (TypeScript 7), `#167` (Tailwind 4), `#136` (non-major bundle).

`#136` is the problem child. Labelled "non-major", it actually bumps **Python 3.12 → 3.14** (and the task-runner **3.11 → 3.14**) across every Dockerfile and CI, carries a `@errand-ai/ui-components` 0.6 → 0.9 jump, and **re-pins `redis` and `kubernetes`** in direct conflict with `#188`/`#185`. As authored it is also broken: `errand/Dockerfile` flips its base to `python:3.14` but keeps a hard-coded `COPY .../python3.12/site-packages` path, and `task-runner/Dockerfile` bumps only the build stage to 3.14 while the runtime stays `gcr.io/distroless/python3-debian12` (Python 3.11) — a wheel/ABI mismatch waiting to happen.

Constraints from `CLAUDE.md`: feature branch + PR per unit of work (never push to main), a `VERSION` bump per PR (CI enforces immutable tags), and local `docker compose up --build` verification before committing.

## Goals / Non-Goals

**Goals:**
- Resolve all nine Renovate PRs, resolving the file overlaps once rather than via serial rebases.
- Land the `cryptography` security fix first, decoupled from the riskier migrations.
- Correctly redistribute `#136`'s contents instead of merging it as-is.
- Keep every merged pass green on all three test suites, plus a runtime smoke test for bumps that touch the running system.

**Non-Goals:**
- No product-behaviour or feature changes; no new capabilities.
- Not touching the five parked in-progress changes (they are stale at 0 tasks).
- No Renovate *policy* changes (grouping, scheduling) — that lives in `errand-ai/.github` per the `ci-pipelines` spec and is out of scope here.

## Decisions

### D1 — One OpenSpec change, four PRs (not one branch, not nine)
The change is the tracking/design umbrella; implementation ships as four independently-mergeable branches, each with its own `VERSION` bump and its own CI/smoke gate. Rationale: a single branch would hold the security fix hostage behind the Tailwind v4 migration; nine separate merges would pay the rebase-cascade tax nine times. Four risk-tiered PRs is the balance.

**Alternative considered — merge Renovate PRs directly, one by one:** rejected. The overlap forces a rebase after every merge, and `#136` can't be merged at all without manual fixes.

**Alternative considered — one mega-PR with everything:** rejected. Couples unrelated risk; a Tailwind regression would block the security patch; hard to bisect.

### D2 — Pass ordering by risk, security first
1. **Security + safe infra** — `#196` crypto (security), `#195` checkout v7, `#141` node 24, `#151` valkey 9 compose + Helm `valkey` chart 0.9.x→0.10.x alignment.
2. **Backend libraries** — `#188` redis 8, `#185` k8s 36, and `#136`'s Python *library* patches (fastapi, sqlalchemy, asyncpg, alembic, psycopg2, openai, docker, litellm image, pytest/pytest-asyncio/fakeredis).
3. **Frontend majors** — `#167` Tailwind 4, `#197` TS 7, `#136`'s `@errand-ai/ui-components` 0.9.
4. **Python 3.13** — errand + task-runner images + CI, done properly (see D4/D6).

Passes 2 and 3 are independent (backend vs frontend) and may proceed in either order or in parallel. Pass 1 first (security); pass 4 last (riskiest, least Renovate-safe).

### D3 — Dissolve `#136` rather than fix-in-place
Close `#136`; its content is split: library patches → Pass 2, `ui-components` 0.9 → Pass 3, Python interpreter (3.13) + Dockerfile fixes → Pass 4. The redis 7.4.1 and `kubernetes <36` re-pins in `#136` are dropped in favour of the `#188`/`#185` majors. This removes the conflicts and the broken Dockerfile in one move.

### D4 — Python interpreter jump as a deliberate, isolated pass
The interpreter jump (to 3.13, per D6) is kept in scope (user asked for all nine) but treated as real work, not a version-string bump:
- `errand/Dockerfile`: update the base **and** the hard-coded `python3.12/site-packages` copy path to `python3.13`.
- `task-runner/Dockerfile`: bump the build stage to `python:3.13-slim-trixie` **and** move the final distroless runtime `python3-debian12` (3.11) → `python3-debian13` (3.13), keeping build and runtime on the same Debian release (trixie) for ABI compatibility. The `gws` binary stays musl-static, so the glibc/musl reasoning in the spec is unaffected.
- CI `python-version` → 3.13.
Verified by a full image build + smoke test, not just the unit suites.

### D5 — Verification bar scales with blast radius
- Pure library/tooling bumps (crypto, checkout, node, TS, Tailwind, ui-components, python libs): **the three test suites** (errand pytest, task-runner pytest, frontend vitest + `vue-tsc -b`).
- Runtime-touching bumps (redis 8, valkey 9, k8s 36, Python 3.13): additionally **`docker compose up --build`** and a smoke test exercising the affected surface (pub/sub, a task run through the runner).
- Frontend majors also get a **manual visual check** (run the app), since vitest won't catch Tailwind v4 utility/removal regressions.

## Risks / Trade-offs

- **Compiled deps lacking wheels for the target interpreter** → source builds or breakage → Mitigation: RESOLVED by preflight — cp314 (and therefore cp313) wheels exist for all compiled deps on the target platforms; 3.13 is comfortably covered.
- **No distroless base provides Python 3.14** (`python3-debian12` is 3.11) → Mitigation: RESOLVED by D6 — target 3.13 on `python3-debian13`, which keeps the task-runner distroless and ABI-matched. This was the driving constraint, now decided.
- **`@errand-ai/ui-components` 0.9 is the real cause of the frontend test failures** (not Tailwind/TS) → Pass 3 scope is larger than a config migration → Mitigation: bisect the three frontend bumps early (apply each alone against vitest) to attribute the failure before committing to Pass 3's shape.
- **Tailwind v4 visual regressions** slip past vitest → Mitigation: manual app run + diff key screens; v4's config format and removed utilities are the usual culprits.
- **redis 8 / kubernetes 36 client behaviour changes** (e.g. redis-py 8 API or connection defaults; k8s client model/enum changes) → runtime break not caught by mocked tests → Mitigation: compose smoke test against real valkey + a task dispatch.
- **Remaining Renovate PRs rebase after each merge** → transient noise → Mitigation: expected; close each Renovate PR as its content lands so Renovate stops re-pushing.
- **`VERSION` collisions** across four PRs → CI immutable-tag failure → Mitigation: bump `VERSION` at the start of each pass's branch; never reuse.

## Migration Plan

Per pass: branch from latest `main` → bump `VERSION` (semver: patch for Pass 1, minor for 2–4) → apply changes → run the pass's verification bar → open PR → confirm CI green (+ smoke test / K8s dry-run for runtime passes per `CLAUDE.md`) → merge → close the corresponding Renovate PR(s) → rebase/refresh the next pass from `main`. **Rollback**: each pass is a single revertable PR; because passes are ordered by increasing risk, a revert of a later pass never disturbs the security fix or safe infra bumps.

## Preflight Findings (resolved 2026-07-12)

- **cp314 wheels — RESOLVED, no blocker.** All compiled backend deps publish linux amd64 + aarch64 (manylinux + musllinux) wheels for CPython 3.14: `psycopg2-binary` 2.9.12 (cp314), `asyncpg` 0.31.0 (cp314), `hiredis` 3.4.0 (cp314). `cryptography` 48.0.1 ships `cp39-abi3` (covers 3.14) plus native cp314. `redis` is pure-Python (`py3-none-any`). Pass 4 will not fall back to source builds on the target platforms.
- **Distroless Python 3.14 — RESOLVED, this is the real constraint.** No distroless base provides Python **3.14**. `gcr.io/distroless/python3-debian13` exists but tracks Debian 13 (trixie) = Python **3.13** (upstream recommends building against `python:3.13-slim-trixie`). Official `python:3.14` / `3.14-slim` Docker images do exist. So the task-runner (whose final stage is distroless, a load-bearing "minimal/hardened" property per its spec) cannot be both distroless **and** 3.14. → decision needed (see D6).
- **`testing/docker-compose.yml` — RESOLVED.** Already on `valkey/valkey:9-alpine` (and `postgres:18-alpine`). Only `deploy/docker-compose.yml` is on `valkey:8-alpine`. Pass 1's valkey bump touches `deploy/` only.
- **Frontend "test" failures — RESOLVED, all red herrings.** The CI `test` job runs `npm ci && vitest`; on all three frontend PRs `npm ci` aborts before vitest runs because Renovate edited `package.json` but did not regenerate `package-lock.json` (the `@errand-ai` scope is on GitHub Packages, unreachable from Renovate's lockfile sandbox). Failures: `#197` = TS 7's native `@typescript/typescript-*` platform binaries missing from the lock; `#167` = tailwindcss 3.4.19 vs 4.3.0 lock mismatch; `#136` = ui-components 0.6.0 vs 0.9.0 lock mismatch. **No vitest or migration breakage is proven** — each bump needs its lockfile regenerated (`npm install`, with GitHub Packages auth) before real test impact can be assessed. Pass 3's mechanical blocker is lockfile regen; the Tailwind v4 config migration remains genuine work.

### D6 — Python interpreter target: 3.13, keep distroless (DECIDED 2026-07-12)
Because no distroless base offers 3.14, standardise the fleet on **Python 3.13** rather than 3.14: errand image → `python:3.13-slim`, task-runner build stage → `python:3.13-slim-trixie`, task-runner final → `gcr.io/distroless/python3-debian13:nonroot`, CI → 3.13. This keeps the task-runner distroless (preserving its hardening spec) and lands ABI-matched build/runtime stages, while still clearing the stale 3.11/3.12 pins. `#136`'s literal 3.14 is treated as "latest interpreter that fits our runtime constraints" = 3.13. **Alternative rejected:** pushing to 3.14 by dropping the task-runner to a non-distroless `python:3.14-slim` runtime — gains one minor version at the cost of the distroless hardening property. **User confirmed 3.13 (keep distroless).**

### Build note — manylinux baseline (discovered in Pass 2)
The root `Dockerfile`'s wheel-download stage pinned `--platform manylinux2014` (glibc 2.17). pip's `--platform` does **not** auto-accept older *or* newer manylinux tags — it matches only the exact stated baseline (plus its own lower aliases). Our pinned deps straddle two baselines: `asyncpg==0.31.0` ships cp312 linux wheels as `manylinux_2_28` only, while `psycopg2-binary==2.9.12` (and `cffi`) ship `manylinux2014`/`_2_17` only. A single `--platform` therefore fails one or the other. Fix: pass **both** `--platform manylinux_2_28_${ARCH}` and `--platform manylinux2014_${ARCH}`; the `python:3.12-slim` (bookworm, glibc 2.36) runtime satisfies both. Verified by a real `docker build --target build` for linux/amd64. Pass 4 (3.13 / trixie, glibc 2.41) inherits this corrected logic — only the `--python-version`/`--abi` change to 313.

### D7 — TypeScript 7 deferred (discovered in Pass 3)
`typescript@7` is the **native (Go) compiler port**, distributed as the `typescript` package with `@typescript/typescript-*` platform binaries and an `exports` map that no longer includes `./lib/tsc`. `vue-tsc` — which the build uses for Vue SFC type-checking (`"build": "vue-tsc -b && vite build"`, also run in CI's image build) — resolves `typescript/lib/tsc` internally, so it crashes under TS 7. Every released `vue-tsc` (through 3.3.7, peer `typescript >=5.0.0`) has this dependency; none supports the native compiler yet. TS 7 is therefore **held at `~6.0.0`** and split out of this sweep; `#197` stays open. Re-attempt when Vue tooling (vue-tsc / vue-language-tools) ships native-compiler support, as its own change. Pass 3 lands Tailwind 4 + ui-components 0.9 without it. (`vite build` itself uses esbuild and is unaffected — only the `vue-tsc` type-check gate blocks.)

## Open Questions

- **`#197` (TypeScript 7) remains open** — deferred per D7, blocked on `vue-tsc` supporting the native compiler. Not closable as part of this sweep.
- D6 (Python target) decided: **3.13, keep distroless.** All preflight questions resolved above.
