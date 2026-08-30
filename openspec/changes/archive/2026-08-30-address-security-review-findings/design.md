## Context

Four findings survived verification against the code: a missing OAuth `state` parameter, an unrestricted SSRF surface in `read_url`, a wildcard CORS policy, and trust-on-first-use SSH host keys. The first two matter; the last two are hardening whose stated exploits do not work as written. The proposal records what was rejected and why, including one finding this change withdrew after discovering the behaviour was specified on purpose.

Two properties of errand shape the fixes:

- **Auth is Bearer-only.** No `set_cookie` anywhere, no `allow_credentials`. This is why the CORS wildcard is not currently exploitable, and it is also what makes the OAuth `state` gap matter: the callback is the one place where a browser-initiated flow hands the server something it must not trust.
- **`read_url` is reachable by the task LLM.** It is an MCP tool, so its caller is a model that may be acting on content it fetched from the internet. The threat is not a human attacker crafting a URL; it is the agent being talked into one.

## Goals / Non-Goals

**Goals:**

- The OIDC authorization flow cannot be completed with a callback the user's browser did not initiate.
- `read_url` and `read_rss_feed` cannot reach link-local, loopback or private address space, including via redirect or DNS.
- CORS is restricted so that introducing cookie auth later does not silently create a vulnerability.
- Known SSH hosts are pinned rather than accepted on sight.

**Non-Goals:**

- Removing or sandboxing `execute_command`. It is the product, and container isolation is the control. See the proposal.
- Changing whether DB-sourced sensitive settings are masked. That is a specified decision with a stated rationale; revisiting it is a separate discussion.
- Restricting the file tools to an allowlist. True as an observation, but the blast radius is a disposable container; the `/shared` mount deserves its own change.
- A general rate-limiting or WAF layer.

## Decisions

**Sign the `state` rather than storing it server-side.** A signed, short-lived value carrying a nonce avoids adding session storage to a server that is otherwise stateless between the authorize and callback requests, and avoids a Valkey round-trip on the login path. The alternative — persisting nonces in Postgres or Valkey — is more conventional but introduces a cleanup obligation and a failure mode where a restart invalidates in-flight logins. Signed state has neither. It must carry an expiry, or a captured value is replayable indefinitely.

**Reject the callback outright on a `state` mismatch, with no fallback.** A tempting compromise is to warn and continue when `state` is absent, so existing in-flight logins are not broken by deploy. That would leave the vulnerability intact for anyone who simply omits the parameter, which is exactly the attack. The cost is that logins started before the deploy and completed after it fail once and must be retried — acceptable and self-correcting.

**Validate URLs after DNS resolution, and again after every redirect.** Blocking on the literal hostname is the common half-measure: `http://127.0.0.1` is caught, `http://localtest.me` (which resolves to 127.0.0.1) is not, and neither is a public host that 302s to `169.254.169.254`. Resolving first and checking the resulting addresses closes both. This means disabling httpx's automatic redirect following and walking the chain manually, which is more code but is the only way to check each hop.

**Accept that DNS rebinding is not fully solved.** Between the validation lookup and the connection, a hostile resolver can change the answer. Fully closing this needs connection-level pinning to the validated IP. That is disproportionate here, and the residual risk is much smaller than the current state of no validation at all. Naming it explicitly so a future reader does not assume the check is airtight.

**An allowlist escape hatch, off by default.** Some deployments legitimately fetch internal hosts — a wiki, an internal feed. Without an escape hatch the fix will be reverted wholesale the first time it blocks something real. An explicit allowlist setting, empty by default, keeps the safe default while making the exception deliberate and visible.

**CORS defaults to an empty origin list, configurable.** The first draft of this decision said "same-origin", but checking the consumers (see Open Questions) showed no supported deployment makes a cross-origin *browser* request at all: the server serves its own frontend in production, Vite proxies `/api` in development, and errand-cloud reaches the API over the WebSocket the server opens outbound. A same-origin request carries no `Origin` header and never consults CORS, so the correct default is to permit no cross-origin request rather than to name the deployment's own origin. Split-origin deployments configure what they need. Keeping `allow_credentials` unset preserves the property that makes the current wildcard harmless.

**Pin SSH hosts where the host is known; keep `accept-new` where it is not.** `git_ssh_hosts` already exists and defaults to `github.com`/`bitbucket.org` — these have published, stable host keys and should be pinned. A blanket `StrictHostKeyChecking=yes` would break cloning from any host not pre-seeded, which is a real workflow. The distinction is between hosts errand already knows about and hosts a user introduces.

## Risks / Trade-offs

**The SSRF fix breaks legitimate fetches** → This is the most likely way the change causes harm. `read_url` is used by real tasks against real sites; an over-broad private-range check that catches a public host makes tasks fail in a way that looks like a network fault. Mitigated by the allowlist escape hatch and by testing against the public URLs tasks actually use, not just synthetic cases.

**Manual redirect walking changes `read_url`'s behaviour** → Redirect limits, relative `Location` headers and cookie handling are all things httpx currently does. Reimplementing the loop risks subtle regressions in ordinary fetches, which matters more than the security case for most tasks.

**Strict `state` validation breaks in-flight logins on deploy** → One failed login per affected user, self-correcting on retry. Accepted deliberately rather than weakened with a fallback.

**CORS restriction breaks an unnoticed consumer** → `errand-cloud` or a local dev frontend on a different port may rely on the wildcard. The default must be same-origin *plus* whatever the deployment configures, and this wants checking against how the cloud proxy actually calls the API before merging.

**Pinning SSH host keys breaks cloning from an unpinned host** → Which is the point, but it will surface as a task failure with a confusing error. The failure message must say what happened and how to add the host.

## Migration Plan

No schema change. Two new settings (URL allowlist, CORS origins) default to values that preserve current behaviour for a standard single-origin deployment.

Order matters: the CORS and SSH changes are independent and safe to land first. The SSRF fix should land with its allowlist setting in the same deployment, or a deployment that needs internal fetches will break with no way to re-enable them. The `state` change is atomic — the authorize and callback halves must ship together.

Rollback is a version revert for everything except in-flight logins, which retry.

## Open Questions

- Should DB-sourced sensitive settings be masked after all? The current behaviour is specified and rationalised ("the admin entered them and needs to see them"), so this is a policy question, not a defect. Masking would cost the settings UI its ability to show a stored secret back for verification. Recorded here because the code will look like a bug to the next reader.
- Should the file tools be restricted for the `/shared` workspace mount specifically? Writing anywhere inside a disposable container is harmless; writing to the user's Google Drive is not.
- ~~Is `read_rss_feed` worth the same treatment as `read_url`, or should it share one validated fetch helper?~~ **Resolved: one shared helper** (`errand/url_guard.py`). The spec requires identical validation for both, and two copies of a security check are how the two drift apart. The coupling concern was that the tools have different failure tolerances, but they do not differ in what they must *refuse* — only in what they do with a response, which stays in each tool.
- ~~Does `errand-cloud` call the API cross-origin?~~ **Resolved: no.** Its browser bundles (`frontend/{admin,cloud}`) fetch only relative paths against errand-cloud's own backend; nothing in them addresses an errand-server origin. The cloud reaches errand-server over the WebSocket the *server* opens outbound (`errand/cloud_client.py`), which is not a browser request and never consults CORS. Local dev is same-origin too — Vite proxies `/api` to `:8000` with `changeOrigin`. So the default is not merely same-origin, it is an **empty** origin list: no supported deployment makes a cross-origin browser request at all.
