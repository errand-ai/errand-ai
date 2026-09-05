## Context

The scan in `errand/local_ai_detection.py` probes a fixed candidate table through the host gateway and registers what answers. It calls `probe_provider_type()` and discards anything that comes back `unknown`. That probe accepts only HTTP 200, so a runtime demanding an API key is discarded along with a port that has nothing on it at all.

Measured on a machine running oMLX:

```
:8000   /v1/models  401  {"error":{"message":"API key required","type":"authentication_error"}}
:8000   /health     200  {"status":"healthy","default_model":"Qwen3.8-27B-MLX-8bit", ...}
:11434  /v1/models  200  {"object":"list","data":[{"id":"qwen3-embedding:0.6b","owned_by":"library"}, ...]}
```

The service is there, it is healthy, it is OpenAI-compatible, and the scan reports that only Ollama was found.

## Decisions

### D1 — A 401 or 403 proves a service; only a body proves a provider

`local-ai-provider-detection` already established this rule and applied it in one direction only: its task 6.1 verified eighteen catalog base URLs by treating 401/403 as proof the endpoint exists and 404 or DNS failure as proof it does not. Detection gets the same rule.

What it does **not** get is a provider row. A row needs a working API key, and the scan has none — the `sk-no-key-required` sentinel is precisely what the service just rejected. Writing it anyway would manufacture a provider that fails on first use, and would do so while reporting success. The scan reports the endpoint as needing a key and stops there.

This keeps `probe_provider_type()` untouched. It answers "what type is this provider", and for an endpoint that will not talk to us `unknown` remains the correct answer; other call sites depend on that. Detection asks a different question — "is something OpenAI-compatible listening here" — and asks it directly.

### D2 — Identify after the key arrives, never before

A 401 carries no `owned_by`, no model list, nothing to identify from. The current fallback would name an oMLX server on port 8000 `vllm`, because that is what the candidate table calls 8000.

Rather than guess, adoption re-probes with the key the user supplied and takes the name from the response — the same `identify_runtime()` path an unkeyed runtime already takes. Naming happens at the first moment the answer is readable.

The alternative, sniffing an unauthenticated `/health`, was rejected. oMLX happens to serve one; that is a property of oMLX, not of OpenAI-compatible servers, and building identification on it would mean a per-runtime table of health endpoints and response shapes — exactly the per-runtime code the fixed candidate table exists to avoid.

### D3 — Adoption creates a `source="detected"` provider

Not `database`. Detected is what it is: found by scanning, labelled as such in the UI, reconciled by later scans, and given the raised request timeout a local runtime's cold start needs.

Creating it as `database` through the existing **Other (OpenAI-compatible)** catalog entry would work on the first day and be wrong on the second: the next scan would find the same endpoint, still see a 401, and report it as an un-adopted runtime needing a key — indefinitely, because nothing would connect the provider the user made to the endpoint the scan keeps finding.

### D4 — A re-scan probes an adopted provider with its own key

This is the subtle one, and getting it wrong deletes a user's provider.

Reconciliation removes `detected` rows whose runtime no longer answers. A keyed runtime probed with the sentinel answers 401 whether it is healthy or long gone. So before probing a candidate endpoint, the scan looks for an existing detected provider with that base URL and probes with **its** stored key:

```
 adopted provider exists for this URL  ->  probe with its key
     200                               ->  present and identified; reconciled as normal
     401 / 403                         ->  present, but the key no longer works: keep the
                                           row and leave the reachability check to say so
     no response                       ->  gone; reconciled away
 no adopted provider                   ->  probe with the sentinel
     200                               ->  registered, as today
     401 / 403                         ->  reported as needing a key
     no response                       ->  nothing here
```

A rotated or revoked key must not delete the provider. Reachability already exists to report that a provider is not working; deletion is for a runtime that has gone.

### D5 — "No body read" and "body read, no marker" are different

`identify_runtime()` falls back to the candidate name when a port is claimed by exactly one runtime. That is a fair inference when a 200 body was read and simply carried no `owned_by` marker.

It is not a fair inference when no body was read at all. Those cases take the endpoint-derived name (`local-ai-<port>`) that a shared port already receives — the existing mechanism for "we do not know", applied to a second way of not knowing.

### D6 — The published server port becomes configurable

`"${ERRAND_PORT:-8000}:8000"` in both compose files. The default is unchanged, so no existing deployment moves; a user running a local OpenAI-compatible server on 8000 gets one variable to set instead of a port conflict with no documented way out.

Dropping 8000 from the candidate table would be worse: it is vLLM's documented default and one of the likeliest ports to find a local runtime on. The collision is errand's to yield, not the scan's.

## Risks

- **A scan now sends a stored API key.** Only to the host gateway, only to candidate ports, and only the key belonging to the provider already recorded at that exact base URL. A key is never sent to an endpoint the user has not already adopted.
- **The adoption prompt is a second cross-repo round trip.** `LlmProviderCard` lives in `errand-component-library`; its scan panel must grow a key field and an Adopt action, which means another release and pin bump, as `local-ai-provider-detection` needed.
- **The port collision persists for anyone who does not set `ERRAND_PORT`.** Defaults cannot both be 8000 and not be 8000; documentation beside the local-AI section is the mitigation.
