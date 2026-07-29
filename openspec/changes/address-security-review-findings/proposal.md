## Why

An LLM-driven security review of ten errand source files (task `639cc280`, qwen3.6-35b-a3b-ud-mlx) produced 30 findings: 12 high, 10 medium, 8 low. Each was checked against the actual code before being accepted here. **Four are genuine. The rest are false, misclassified, hallucinated, or describe deliberate design decisions**, so this change addresses the four and records why the others were rejected — the rejections matter as much as the acceptances, because the report reads as authoritative and will be found again.

The reviewing model demonstrably hallucinated during the run: its per-file report for `mcp_server.py` contained sixty invented "findings" (`read_url doesn't handle DNS orchestration`, `…DNS sinkholing`, `…DNS fast flux`), most annotated "not an issue" or "same as previous". It caught and corrected itself mid-task, but the output cannot be taken at face value.

### Verified — genuine

| # | Finding | Evidence |
|---|---|---|
| 1 | **OAuth flow has no `state` parameter** | `state` appears zero times in `errand/auth_routes.py`. The Authorization Code flow has no CSRF protection, contrary to RFC 6749 §10.12 |
| 2 | **`read_url` is an unrestricted SSRF surface** | `errand/mcp_server.py` fetches any URL with `follow_redirects=True`, no scheme check, no private-IP block. Reachable by any task LLM through MCP |
| 3 | **CORS allows every origin, method and header** | `errand/main.py:427` — `allow_origins=["*"], allow_methods=["*"], allow_headers=["*"]` |
| 4 | **SSH host keys accepted on first use** | `StrictHostKeyChecking=accept-new` at three sites: `container_runtime.py:551`, `task_manager.py:338`, `plugin_marketplace.py:213` |

Findings 1 and 2 are materially serious. Findings 3 and 4 are hardening, and their severity is lower than the report claims:

**CORS.** The report's scenario — *"a malicious page sends a DELETE to `/api/llm/providers/{id}` when an authenticated admin visits it"* — does not work. errand authenticates with Bearer tokens only: no `set_cookie` anywhere, and `allow_credentials` is not set. A browser will not attach the `Authorization` header to a cross-origin request it did not author, so the forged request arrives unauthenticated and is rejected. The wildcard currently exposes only endpoints that are already public. It is worth tightening because it becomes genuinely dangerous the moment cookie auth is introduced, not because it is exploitable today.

**SSH `accept-new`.** Trust-on-first-use, not "disabled verification" as the report states. It accepts an unknown host key on first contact and pins it thereafter, so an attacker must be in position at exactly that moment. Worth pinning known hosts; not urgent.

### Withdrawn on further checking

An earlier draft of this proposal listed a fifth finding: that `resolve_settings` masks sensitive values only when `source == "env"`, so DB-stored secrets (`mcp_api_key`, `hindsight_token`, `oidc_client_secret`) are returned in full by `GET /api/settings`.

The code does behave that way, but it is **deliberate and specified**. `settings-registry` states it twice, with rationale: *"Sensitive settings sourced from the database SHALL be returned in full (the admin entered them and needs to see them)"*, backed by the scenario "DB-sourced sensitive value shown in full". Reversing it is a policy change, not a bug fix, and it would stop the settings UI showing a stored secret back for verification.

Whether that policy is still right is a fair question — defence in depth would argue an admin should re-enter rather than read back — but it belongs in a design discussion, not in a list of defects. Recorded as an open question rather than silently dropped, because the same code will look like a bug to the next reader.

This was the same error the source report makes throughout: treating an intentional decision as an oversight because the code looks wrong in isolation.

The report's own version of this (H12: `/api/settings` returns SSH private keys) is simply false — `ssh_private_key` is in `EXCLUDED_KEYS`.

### Rejected, with reasons

- **H1 — "arbitrary shell execution via `execute_command`, `shell=True`"**. This is the product, not a defect. The task-runner exists to execute agent-authored commands inside a disposable container. The proposed mitigation ("remove or heavily restrict `execute_command`") would remove errand's core capability. Container isolation is the control, and it is already in place.
- **H9 — "cloud callback does not verify token signature"**. The token is decoded unverified only to read `sub`/`email`, and it was just retrieved by the server itself from the cloud token endpoint over TLS. Exploiting it requires already controlling that exchange. Worth verifying as defence in depth, but not HIGH. Note the same unverified-decode pattern in `_validate_token` (`main.py:515`) is legitimate: it peeks at `iss` to select a key, then re-verifies with HS256 and the issuer pinned.
- **H12 as written** — false, see above.
- **H6 (timing side-channel), H8 (regenerate endpoint returns the new key), H10 (task_id not UUID-validated)** — speculative or by design. H8 in particular: a regenerate endpoint must return the generated key once.
- **M2 (bcrypt 72-byte limit), M3 (`AUTO_MIGRATE`), L1–L3 (public version/health/metrics endpoints)** — operational trade-offs, not vulnerabilities.
- **M9 (file tools have no path allowlist)** — true as stated, but the blast radius is a disposable container. Worth revisiting only for the `/shared` workspace mount, which is real user data; filed as a follow-up rather than a fix here.
- **`mcp_server.py` L41–L100** — hallucinated.

## What Changes

- Add a cryptographically random `state` parameter to the OIDC authorization request, store it server-side or in a signed cookie, and reject callbacks whose `state` does not match.
- Validate URLs in `read_url` (and `read_rss_feed`, which shares the defect): require `http`/`https`, reject literals and DNS names resolving to private, loopback, link-local or metadata ranges, and re-check after each redirect.
- Restrict CORS to configured origins, defaulting to the deployment's own origin rather than `*`.
- Pin SSH host keys where a known host is expected, keeping `accept-new` only where first contact is genuinely unavoidable.

## Capabilities

### New Capabilities

None. Each change tightens behaviour in an existing capability.

### Modified Capabilities

- `frontend-auth`: the OIDC authorization flow gains `state` generation and validation.
- `mcp-server`: `read_url` and `read_rss_feed` gain URL validation.
- `container-runtime`: host-key policy.

CORS has no owning spec today. Its requirement goes in `frontend-auth`, which already governs how browsers reach the API, rather than inventing a capability for one middleware line.

`settings-registry` is **not** modified: see the withdrawn finding above.

## Impact

- **Code**: `errand/auth_routes.py`, `errand/mcp_server.py`, `errand/settings_registry.py`, `errand/main.py`, `errand/container_runtime.py`, `errand/task_manager.py`, `errand/plugin_marketplace.py`.
- **Breaking**: restricting CORS will break any client on an origin not in the allowlist; the default must be chosen so a standard single-origin deployment is unaffected. Masking DB-sourced secrets changes `GET /api/settings` responses — any UI that reads a secret's value back will now receive a mask, which is the point, but wants checking against the settings cards.
- **Risk of the SSRF fix**: over-tight validation breaks legitimate fetches. `read_url` is used by real tasks against real sites, so the private-range block must not catch ordinary public hosts, and a deployment fetching an internal wiki will need an explicit allowlist escape hatch.
- **Not addressed**: findings rejected above. `M9` (file-tool path allowlist for `/shared`) is worth its own change.
- **Provenance**: the source report is the output of task `639cc280`. Treat it as a lead generator, not an authority — a 5-of-30 hit rate, with fabricated entries among the rest.
