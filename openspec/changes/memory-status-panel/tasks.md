## 1. Branch and version

- [ ] 1.1 Create branch `memory-status-panel` from an up-to-date `main`
- [ ] 1.2 Bump `VERSION` (minor — new API surface and a new settings card)

## 2. Establish the upstream contract

First, because the shape of every panel depends on what a real instance returns, and discovering a field is absent after the UI is built means reworking it.

- [ ] 2.1 Against a running memory service, capture actual responses for liveness, readiness, version, bank statistics, the memory time series, failed operations and token usage
- [ ] 2.2 Confirm which feature flags the deployed version reports, and which panels each one gates
- [ ] 2.3 Record any field that is absent or shaped differently from the design in `design.md`

## 3. Proxy

- [ ] 3.1 Write failing tests: an allowed route returns upstream data; a non-enumerated upstream path is refused; responses never contain the configured token or base URL; not-configured and unreachable are distinct and neither is a server error
- [ ] 3.2 Implement the proxy with an explicit enumeration of allowed upstream routes
- [ ] 3.3 Take the bank as a parameter on every bank-scoped route, defaulting to the configured bank
- [ ] 3.4 Sanitise upstream errors so no upstream URL or authorisation detail is echoed
- [ ] 3.5 Implement the pollable status route so it calls only upstream liveness — assert in a test that no readiness or statistics call is made
- [ ] 3.6 Implement statistics, time series, failed operations and token usage as explicitly requested routes
- [ ] 3.7 Implement the LLM check as an explicit action, reporting "unavailable" when the upstream check is disabled

## 4. Enable the upstream LLM health check

- [ ] 4.1 Set `HINDSIGHT_API_ENABLE_BANK_LLM_HEALTH=true` on the bundled memory service in both compose files
- [ ] 4.2 Verify the check returns a real result rather than the "disabled" response
- [ ] 4.3 Verify that with the flag unset the proxy reports unavailable rather than failure

## 5. Settings card

- [ ] 5.1 Write failing frontend tests: healthy, unreachable and not-configured states each render distinctly; no token value ever appears in output; no request goes anywhere but the errand server
- [ ] 5.2 Build the card: health, version, bank, counts, last write, growth indicator
- [ ] 5.3 Add the failed-operations panel exposing error message and retry state
- [ ] 5.4 Add the token usage panel, gated on the reported tracing feature
- [ ] 5.5 Add the user-triggered LLM check control with inline outcome
- [ ] 5.6 Map upstream fact-type identifiers to errand's own labels, and assert in a test that the raw identifiers never reach the rendered output
- [ ] 5.7 Render the memory service URL state and bearer as read-only, with no editing controls

## 6. Navigation and capability

- [ ] 6.1 Decide the card's placement in settings navigation and record the decision in `design.md`
- [ ] 6.2 Advertise the card through the capabilities mechanism so it appears only where memory is a configured feature
- [ ] 6.3 Confirm the card is absent, rather than broken, on a deployment with no memory service

## 7. Browse and export

- [ ] 7.1 Decide whether export ships in this change; if deferred, record why in `design.md` and remove the remaining tasks in this section
- [ ] 7.2 Add browse and search over stored items, paginated
- [ ] 7.3 Add export, streamed or size-capped rather than buffered

## 8. Verify

- [ ] 8.1 Run the full errand and frontend test suites
- [ ] 8.2 Exercise the card against a healthy service, a stopped service, and a deployment with memory unconfigured
- [ ] 8.3 Confirm from the memory service's own logs that polling the card does not generate statistics or LLM calls

## 9. Archive

- [ ] 9.1 `openspec archive memory-status-panel -y` and commit the result in this PR

## Post-merge notes

- If bank statistics prove expensive on a large bank under the shared database, move the on-view fetch behind an explicit refresh.
- Per-task memory attribution — tagging retains with the originating task id so a task page can show what it remembered — is a separate change that would extend this card's data rather than replace it.
