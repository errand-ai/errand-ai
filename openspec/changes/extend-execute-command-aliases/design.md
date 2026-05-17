# Design — extend execute_command aliases

## Context

PR #181 added a static alias mechanism: each entry in `EXECUTE_COMMAND_ALIASES` becomes an always-on `@function_tool` shim that delegates to `_execute_command_impl`. The aliases are visible to the SDK's tool registry at agent construction time, so when the model calls `run_command(...)` the SDK finds it and dispatches normally.

That mechanism works for any failure mode where the model emits an exact alternative name. It does NOT work when the model emits:

1. A new alternative name we haven't seen before (`executescript`)
2. A known name with non-alphanumeric junk appended (`run_command<|channel|>json`)

Case 1 is solved by simply adding to the alias list. Case 2 requires a name-normalization step.

## Decision

Two layered changes:

### Layer 1 — extend the static alias set

Add `executescript` to `EXECUTE_COMMAND_ALIASES`. Final tuple:
```
("run_command", "bash", "shell", "sh", "executescript")
```

Optional additions to defer until we see them in production:
- `execute_script` (snake_case variant of executescript)
- `python` (some models call `python` to mean "run this code")

Keep the alias set small. Each entry costs an SDK tool slot and clutters the function-tool list passed to the LLM in the tool schema. Adding speculatively is more harmful than reactive additions.

### Layer 2 — Harmony-suffix normalizer in the recovery handler

When the SDK raises `ModelBehaviorError("Tool X not found in agent TaskRunner")`, the existing recovery handler in `task-runner/main.py` (added in PR #178) parses the error message to extract the tool name and decides whether to enable a known-but-not-yet-enabled MCP tool. Extend that handler:

1. Capture the failing tool name as-is (e.g. `run_command<|channel|>json`).
2. Apply a normalization regex: strip everything from the first occurrence of `<|` onward. So `run_command<|channel|>json` becomes `run_command`.
3. If the normalized name is in `all_known_tools` OR in `EXECUTE_COMMAND_ALIASES` OR equals `"execute_command"`:
   - Log a structured event noting the original name, the normalized name, and the model identifier (so we can track which models leak Harmony tokens)
   - Re-dispatch the call via the normalized name's tool
   - Treat the original call's arguments verbatim (do not strip from arguments — only from the tool name)
4. If the normalized name is still unknown, fall through to the existing "tool not found" handling.
5. Bound recovery per `(original, normalized)` pair via `HARMONY_RECOVERY_CAP_PER_PAIR` (default `3`). Once a pair exceeds the cap, log a cap-reached warning and let `MAX_AGENT_RETRIES` absorb further attempts — a model that keeps emitting the same bad token cannot loop indefinitely.

The normalizer is deliberately narrow — it only fires on the `<|` prefix that marks Harmony tokens. We do NOT do general fuzzy matching or Levenshtein distance, which would risk dispatching to the wrong tool.

## Alternatives considered

### A. Add aliases for every observed bad name forever

Reject — adds linear-in-failures bloat to the alias list, every alias is advertised to the LLM as a callable tool which dilutes the tool catalog. The normalizer addresses the *class* of Harmony-suffix failures generically.

### B. Modify the OpenAI Agents SDK to strip Harmony tokens before tool dispatch

Reject — third-party dependency, slow to upstream, and the Harmony format is an OpenAI-internal convention that future SDK versions may format differently. Keeping the fix in our recovery handler keeps it under our control.

### C. Pre-process the model's output stream to strip Harmony tokens before they reach the SDK

Reject — would require intercepting the model output stream and rewriting it, which crosses an abstraction boundary that the agents SDK owns. High risk of breaking other Harmony-format constructs (chain-of-thought channels, etc.).

### D. Always-on regex normalizer in the SDK call site (no recovery path)

Considered. Cleaner in some ways — the SDK would always see the canonical name. But the existing recovery handler is the right place because (a) it already runs only on error, so the happy path is unaffected, (b) it logs failures, which we want for observability, and (c) it lets us scope the normalization to "names we recognize" instead of "any string with a `<|` in it".

Chose D's spirit (a normalizer scoped to recognized names) but kept it inside the existing recovery handler rather than at the SDK call site — that way we get telemetry on every normalization event and the happy path is unaffected. Option B (modifying the Agents SDK) was explicitly rejected above.

## Open questions

- Should the normalizer be unit-tested against the actual Harmony token alphabet (e.g. `<|start|>`, `<|message|>`, `<|return|>`, `<|channel|>`)? Or is the generic `<|.*` regex sufficient? Lean: generic regex + a small fixture of real examples from logs.
- Do we need to track the `model` field on the normalization log so we can correlate with which models leak? Yes — include the `model_setting.model` value in the log structured field.
