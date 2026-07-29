## 1. Branch and version

- [ ] 1.1 Create branch `address-security-review-findings` from an up-to-date `main`
- [ ] 1.2 Bump `VERSION` (minor — behaviour changes to auth, CORS and outbound fetching)

## 2. OAuth `state` (highest value)

The one materially serious finding alongside the SSRF. Both halves must ship together — an authorize that sets `state` without a callback that checks it is no better than today.

- [ ] 2.1 Write failing tests first: the authorization URL carries a `state`; a callback with matching state proceeds; missing, mismatched and expired state are each rejected; a rejected callback establishes no session and returns no tokens
- [ ] 2.2 Generate a signed, expiring `state` bound to the initiating browser, and include it in the authorization request
- [ ] 2.3 Validate it on callback, rejecting outright on any failure
- [ ] 2.4 Confirm there is **no** permissive fallback — an absent `state` must fail, not warn and continue. A fallback leaves the vulnerability fully intact for anyone who simply omits the parameter
- [ ] 2.5 Confirm the rejection path returns no tokens to the browser and creates no session

## 3. SSRF in URL-fetching tools

Riskiest change in this set: `read_url` is used by real tasks against real sites, so over-tight validation looks like a network fault rather than a policy decision.

- [ ] 3.1 Write failing tests first: loopback, link-local (`169.254.169.254`), and private ranges refused; `file://` refused; a public hostname that **resolves** to loopback refused; an ordinary public URL still fetched
- [ ] 3.2 Write a failing test for the redirect case: a permitted public URL redirecting to a private address is not followed
- [ ] 3.3 Implement validation against **resolved addresses**, not the hostname string — a literal-only check misses names like `localtest.me`
- [ ] 3.4 Replace automatic redirect following with a manual loop that re-validates each hop. Preserve the existing redirect limit and relative-`Location` handling; this is where ordinary fetches are most likely to regress
- [ ] 3.5 Add the allowlist setting, empty by default, with tests for allowlisted-permitted and non-allowlisted-refused
- [ ] 3.6 Apply the same validation to `read_rss_feed`, which shares the defect. Decide whether both tools call one shared validated-fetch helper (see design open question)
- [ ] 3.7 Verify against the public URLs real tasks actually fetch, not only synthetic cases. A false positive here breaks working tasks
- [ ] 3.8 Note in the code that DNS rebinding between validation and connection is **not** closed by this — a future reader must not assume the check is airtight

## 4. CORS

Hardening, not a live fix: errand is Bearer-only with no cookies, so the wildcard is not currently exploitable. It becomes dangerous if cookie auth is ever added.

- [ ] 4.1 Write failing tests: default configuration does not allow `*`; a configured origin is permitted; an unconfigured origin is refused
- [ ] 4.2 Replace the wildcard with a configured origin list defaulting to the deployment's own origin
- [ ] 4.3 Leave `allow_credentials` unset — it is what makes the current wildcard harmless, and enabling it alongside a loose origin list would be worse than today
- [ ] 4.4 **Check `errand-cloud` before merging.** If the cloud proxy calls the API cross-origin, a same-origin default breaks it. This is the most likely way this change causes an outage

## 5. SSH host keys

Lowest severity — trust-on-first-use, not disabled verification.

- [ ] 5.1 Write failing tests: a pinned host with a mismatched key is refused; an unknown host still uses first-use acceptance
- [ ] 5.2 Pin known-hosts entries for the hosts in `git_ssh_hosts`
- [ ] 5.3 Keep `accept-new` for hosts with no pinned key, so user-supplied remotes still clone
- [ ] 5.4 Apply consistently across all three call sites: `task_manager.py:338`, `plugin_marketplace.py:213`, `container_runtime.py:551`
- [ ] 5.5 Make the mismatch error name the host and the cause — otherwise it reads as a network failure

## 6. Verify

- [ ] 6.1 Backend suite green
- [ ] 6.2 Complete a real OIDC login end-to-end against Keycloak — the `state` change touches the one flow that locks everyone out if it breaks
- [ ] 6.3 Confirm a task using `read_url` against a normal public site still succeeds
- [ ] 6.4 Confirm the frontend still reaches the API with the new CORS default
- [ ] 6.5 Confirm a git clone from `github.com` still works with pinned keys

## 7. Ship

- [ ] 7.1 Commit, push, open a PR
- [ ] 7.2 CI green
- [ ] 7.3 Deploy and confirm login works **before** merging. An auth regression here is a lockout, not a degradation
- [ ] 7.4 Merge, delete branch

## 8. Deliberately not addressed

Recorded so they are not re-raised from the same report. Reasoning is in the proposal.

- [ ] 8.1 `execute_command` with `shell=True` — the product, not a defect. Container isolation is the control
- [ ] 8.2 DB-sourced sensitive settings returned unmasked — specified behaviour with a stated rationale. Revisit as a policy question if wanted, not as a bug
- [ ] 8.3 File tools have no path allowlist — true, but the blast radius is a disposable container. Worth its own change for the `/shared` mount, which is real user data
- [ ] 8.4 Unverified JWT decode at the cloud callback — the token was just fetched by the server over TLS. Worth verifying as defence in depth; not the HIGH the report claims. Do **not** "fix" the similar-looking decode in `_validate_token` (`main.py:515`) — it peeks at `iss` to select a key and then re-verifies properly
