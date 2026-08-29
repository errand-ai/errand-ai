## Why

Twelve Renovate PRs are open against this repository, eight of them labelled `[SECURITY]`. Merged one at a time they are eight rebase-and-rebuild cycles — the four npm ones all mutate `frontend/package-lock.json` and so conflict with each other pairwise. Merged as a set they still leave holes: `npm audit` reports **nine** advisories in `frontend/`, and the four `[SECURITY]` PRs cover only four of them.

This change closes every known advisory in one pass, and records which of them actually reach a user.

### What actually ships

The `[SECURITY]` label is a poor severity signal here. The split that matters is whether the package reaches a browser:

| Package | Severity | Advisory | Ships? |
|---|---|---|---|
| `marked` | high | CVE-2026-41680 — `\x09\x0b\n` drives the tokenizer into unbounded recursion until the tab OOMs | **yes** |
| `dompurify` | moderate | CVE-2026-65900 and others — `SAFE_FOR_TEMPLATES` / `IN_PLACE` sanitisation bypasses | **yes** |
| `vite` | high | `server.fs.deny` bypass on Windows alternate paths | dev only |
| `postcss` | high | path traversal via `sourceMappingURL` reads arbitrary `.map` files | dev only |
| `nanoid` | high | custom generators loop indefinitely at size zero (via `postcss`) | dev only |
| `undici` | high ×3 | TLS validation bypass, header injection (via `jsdom`) | dev only |
| `js-cookie` | high | prototype hijack in `assign()` (via `@vue/test-utils`) | dev only |
| `brace-expansion` | high | DoS via exponential expansion (via `@vue/test-utils`) | dev only |
| `esbuild` | low | arbitrary file read from the dev server on Windows | dev only |

`dompurify` and `marked` are runtime dependencies of `@errand-ai/ui-components` and land in the production bundle. Everything else is a devDependency reached only on a CI runner or a developer's machine — real, but a different exposure class.

**`marked` is the sharpest item here.** It renders task output, which is LLM- and tool-generated content. A three-byte sequence in a tool result is enough to OOM the tab. That is a shorter path than most of what a source-code review turns up.

`dompurify` has bitten this repository before — `frontend/src/components/__tests__/TaskOutputModalXssRegression.test.ts` exists because of a pre-3.3.2 bypass.

Five of the nine (`undici`, `js-cookie`, `brace-expansion`, `esbuild`, and `nanoid` beyond what the `postcss` PR reaches) have **no open Renovate PR at all**. Merging the four `[SECURITY]` npm PRs would leave them open.

### Python side

| Package | Manifest | Assessment |
|---|---|---|
| `cryptography` 48.0.1 → 50.0.0 | `errand/requirements.txt` | **Not exploitable here.** CVE-2026-69247 is a Bleichenbacher oracle in `pkcs7_decrypt_*`; errand uses `Fernet` (`llm_providers.py`) and `Ed25519` (`main.py:13`) and calls no PKCS#7 API. Worth taking as currency, not as a fix. |
| `pytest` 8.3.4 → 9.0.3, `requests` 2.32.3 → 2.33.0 | `workspace-gateway/requirements-test.txt` | Test-only. `requests` also ships in the refresher image, so the pin is load-bearing there. |
| `mcp` 1.2.0 → 1.28.1 | `evals/requirements.txt` | **Fixes nothing real.** The CVEs are server-side DoS in Streamable HTTP; the eval driver is a pure MCP *client*. Taken to clear the alert and to stop a 26-minor-version drift, not because it closes an exposure. |

### A gap Renovate cannot see — and why it is not fixed here

`errand/requirements.txt` specifies `mcp[http]>=1.23.2,<2` — a range on the process that *runs* `mcp_server.py`, which is the one place the mcp DoS advisories genuinely apply. It resolves to a patched version today, but "we are not vulnerable because pip resolved favourably at build time" is not a control, and no Renovate PR addresses it because the range is already satisfied.

The obvious reflex is to pin it here. That reflex is wrong twice over.

**First, the range is load-bearing.** On 2026-07-28 mcp 2.0.0 was published and removed `mcp.server.fastmcp`, which `errand/mcp_server.py:15` imports. errand's requirement had no upper bound, so the next Docker build resolved to 2.0.0 and pytest failed at collection — zero tests ran. `task-runner` survived because `openai-agents` declares `mcp<2,>=1.19.0` transitively; `evals` survived because it pins `==1.2.0`. The `<2` was added the same day in commit `05c3791`, slipped into a PR titled "Restore MCP server configuration UI". It is a deferral guarding an unmigrated API, not an oversight, and it stays until someone ports `mcp_server.py` to the 2.0 surface.

**Second, `mcp[http]` is not an outlier.** 17 of the 27 requirements in that file are ranges. Pinning one of them because an advisory pointed at it leaves the file neither pinned nor ranged, and invites the next reader to assume the pinned ones were pinned for a reason.

The lesson actually recorded from that incident was not "pin every line" — it was that errand's Docker build resolves dependencies fresh on every run with few upper bounds, and that a **constraints file or lockfile** would make builds reproducible without giving up transitive patch uptake. That is a different remedy from per-line pins, and a better one. It deserves its own change. Recorded here so the float is not re-raised as a fresh discovery. See Open Questions in `design.md`.

## What Changes

- Resolve all nine `frontend/` npm advisories with a single `npm audit fix` (every fix is non-major — `npm audit --json` reports `fixAvailable: true`, a plain boolean rather than an object, for all nine, so no `--force` and no major bumps).
- Bump `cryptography` to `50.0.0` in `errand/requirements.txt`.
- Bump `pytest` to `9.0.3` and `requests` to `2.33.0` in `workspace-gateway/requirements-test.txt`.
- Bump `mcp` to `1.28.1` in `evals/requirements.txt`.
- Correct the `ci-pipelines` spec, which asserts that no `renovate.json` exists in this repository. One does, at the repository root, extending the org preset — added in `d1415d9` and amended in `4e49850`. The spec has been wrong since then.
- Close Renovate PRs #218, #219, #221, #230, #231, #232, #233 and #240 as superseded, each with a one-line reason.

**Not in scope**, and left open:

- **#204 (non-major)** — carries Python 3.13 → 3.14 across four Dockerfiles and the CI workflow, plus `fastapi` 0.139 → 0.141 and `openai` 2.45 → 2.54. That is an infrastructure change wearing a dependency costume, and it is not security-labelled.
- **#226 (jsdom v30)**, **#209 (pinia v4)**, **#197 (typescript v7)** — majors, not security-labelled. #226 would clear the `undici` cluster, but `npm audit fix` already does that within `jsdom@29`.
- **Pinning the seventeen ranged runtime requirements** — see above.

## Capabilities

### New Capabilities

None. Version bumps change no requirement.

### Modified Capabilities

- `ci-pipelines`: the "Dependency-update automation via Renovate" requirement asserts that this repository contains no `renovate.json`. It does. The requirement is corrected to describe the minimal root config that extends the org preset, preserving the intent (policy lives centrally) while matching reality.

## Impact

- **Code**: `frontend/package-lock.json`, `errand/requirements.txt`, `evals/requirements.txt`, `workspace-gateway/requirements-test.txt`, `workspace-gateway/Dockerfile.refresher`. No application source changes.
- **Found during implementation**: `Dockerfile.refresher` pinned `requests==2.32.3` — the vulnerable version — while `requirements-test.txt` carries the comment *"keep it pinned to the image's"*. Renovate PR #218 bumped only the test file, so merging it alone would have left the vulnerability in the running refresher image while making the test pin claim it was fixed. Both are bumped. This is the clearest example of the proposal's thesis: the `[SECURITY]` label tracks the manifest Renovate can parse, not the artefact that ships.
- **Breaking**: none expected. All npm fixes are non-major. `cryptography` crosses two majors, but errand's usage is confined to `Fernet` and `Ed25519` key handling, both stable across the range.
- **Risk**: concentrated in `marked` and `dompurify`, because they are the two that actually render output. A sanitiser or tokenizer change can alter how existing task output displays. This is the part that wants looking at in a browser, not just a green test run.
- **Deliberately separate from `address-security-review-findings`**: that change rewrites the OIDC callback and the CORS policy, and its own tasks note that an auth regression there is a lockout rather than a degradation. Landing a `cryptography` major bump and a frontend lockfile rebuild in the same deploy would give a broken login or a blank frontend two candidate causes instead of one. The two changes address the same programme of work and are intentionally not the same deploy.
