## 1. Setup

- [x] 1.1 Create feature branch `stall-detector-signature-precision` from `main`.
- [x] 1.2 Bump `VERSION` — **MINOR**, 0.139.0 → 0.140.0. Written as PATCH before the
      soft-nudge merge; the change now adds a new capability (nudge tier) and a new
      operator-facing env var (`STALL_NUDGE_LIMIT`), which is a backwards-compatible
      feature addition, not a correction.

## 2. Resolve design open questions

- [x] 2.1 Audit the return types of the task-runner's tools and confirm `str(result)`
      is stable across identical invocations (no embedded object addresses,
      timestamps, or ordering nondeterminism). Record any tool for which the digest
      can never repeat — the guard silently degrades to "never trips" for those.
      *Done 2026-07-27 — see "Audit: is `str(result)` stable?" in design.md. No
      reprs/addresses; `duration_ms` is outside `output`; MCP results are dict reprs;
      `discover_tools` is deterministic on repeat; blind tools are `retain`,
      `query_loki_logs`, `web_search`, `browser_navigate`.*
- [x] 2.2 Confirm overriding `Agent.get_all_tools()` to attach guardrails does not
      disturb the existing `ToolFilterCallable` lazy tool-visibility machinery — both
      shape the per-turn tool list.
      *No conflict. The filter is attached to the MCP **servers**
      (`main.py:1985 server.tool_filter = tool_filter`), not the agent, so it decides
      which tools appear in the list `get_all_tools()` returns; the override merely
      decorates whatever survives filtering. `Agent` is a dataclass and subclasses
      cleanly (verified). One caveat: native tools are module-level `@function_tool`
      singletons, so attaching mutates shared state — the override must be idempotent
      or tests will leak guardrails between cases.*
- [x] 2.3 Confirm the existing error classification/retry path fires before the stall
      guard could see a third identical tool *failure*, so repeated identical errors
      are not reclassified from their real cause into `stalled`.
      *Ordering is fine — `except AgentStallError` precedes `except
      ModelBehaviorError` in the retry loop. **But a worse hazard was found in the
      opposite direction:** `run_internal/tool_execution.py:919-928` wraps any
      non-`AgentsException` raised inside a tool output guardrail into
      `UserError(f"Error running tool {name}: {e}")`. `AgentStallError` currently
      extends plain `Exception`, so raising it from the guardrail would be silently
      reclassified and the `stalled` handler would never fire. Fix: make
      `AgentStallError` subclass `agents.exceptions.AgentsException`, which the wrap
      site re-raises unchanged. Added as task 3.7.*
- [x] 2.4 Grep the skill scripts under `system-skills/` and the DB/git skill sources
      for commands that are invoked with identical arguments, advance state, and print
      nothing to stdout.
      *`system-skills/` contains only SKILL.md files — no scripts, no risk. DB/git
      skills are not in this repo, so verified against production telemetry instead,
      which is stronger evidence since it covers the skills actually in use. Every
      high-volume `"(no output)"` repeat found is a **stall, not progress**: pod
      `task-runner-2904f9da-xz7dd` (task `5826afe4`) called
      `parse_queue.py /shared/BlogsToProcess.md 10` with byte-identical arguments
      **192 times**, every one returning `"(no output)"`, and ran to
      `MaxTurnsExceeded(200)`. The two-tier guard would have nudged at 3 and aborted
      at 6. No state-advancing silent command was found anywhere in 7 days of logs;
      the risk stays documented in design Risks as theoretical.*
- [x] 2.5 Decide whether to explicitly skip recording for the known-blind tools so the
      limitation is declared in code rather than emergent.
      *Decision: **do not** skip-list them. Blind tools are blind because their results
      genuinely differ per call, so recording them is already a no-op — the counter
      simply never accrues. An explicit list would add maintenance burden, go stale if
      a tool's output becomes stable (e.g. `retain` returning a fixed ack), and
      actively suppress a real stall if one of them ever did start repeating. The
      blindness is documented in the design audit instead.*

## 3. StallDetector rewrite

- [x] 3.1 Change `StallDetector` state from `dict[str, int]` to a per-key record
      holding the last result digest and the consecutive-identical-result count.
- [x] 3.2 Add result digesting: SHA-256 over the complete `str(result)` (explicitly
      not the `_truncate`d form used for transcript events).
- [x] 3.3 Change `record()` to take the tool result alongside tool name and arguments;
      increment when the digest matches the stored one, reset to 1 and replace the
      digest otherwise. Preserve the `limit <= 0` disabled behaviour (return 0) and
      the canonical-args/`repr` fallback.
- [x] 3.4 Leave `DEFAULT_STALL_REPEAT_LIMIT` at 6 and add
      `DEFAULT_STALL_NUDGE_LIMIT = 3`. Update the module comment to describe the
      result-aware rule and the two tiers.
- [x] 3.5 Track, per key, whether it has already been nudged this attempt, so a key is
      nudged at most once. Ensure recording uses the tool's own result so a nudge never
      resets a counter.
- [x] 3.7 Make `AgentStallError` subclass `agents.exceptions.AgentsException` so the
      SDK's tool-guardrail wrap site re-raises it unchanged instead of converting it
      to `UserError` (found in 2.3 — would have silently broken the `stalled` path).
- [x] 3.6 Read `STALL_NUDGE_LIMIT` from env (default 3; `<= 0` disables the nudge tier
      only; unparseable → warn + default; `>= STALL_REPEAT_LIMIT` → treat as disabled
      with a warning rather than reordering the tiers).

## 4. Wire in via a tool output guardrail

- [x] 4.1 Remove the `stall.record(...)` call from the `tool_called` branch of the
      streaming loop. The stream handler goes back to emitting events only.
- [x] 4.2 Add a `ToolOutputGuardrail` that reads `context.tool_name`,
      `context.tool_arguments`, and `output` from `ToolOutputGuardrailData` and calls
      `stall.record(...)` with the pre-substitution result.
- [x] 4.3 Return `ToolGuardrailFunctionOutput.allow()` below the nudge threshold; at
      `STALL_NUDGE_LIMIT` (first time only for that key) emit `stall_nudge` and return
      `reject_content(<nudge text>)`; at `STALL_REPEAT_LIMIT` emit `stall_detected` and
      abort — either by raising `AgentStallError` directly or via `raise_exception()`,
      whichever surfaces the existing `stalled` classification and message shape
      intact. Verify the abort path is not swallowed and reclassified as
      `ToolOutputGuardrailTripwireTriggered`.
- [x] 4.6 Write the nudge text as a fixed template interpolating only tool name and
      repeat count, pointing at `submit_result` (per design D5 — the spike shows the
      nudge moves dithering, not repetition). Do not echo tool-supplied content into
      it.
- [x] 4.4 Subclass the agent to override `get_all_tools()`, attaching the guardrail to
      every returned `FunctionTool` so MCP tools are covered too
      (`mcp/util.py:304` omits guardrails). Make the attachment idempotent — the
      method runs per turn.
- [x] 4.5 Confirm a fresh `StallDetector` is bound per agent attempt so counts and
      digests never leak across retries, and that the guardrail closes over the
      current attempt's detector rather than a stale one.

## 5. Event payload

- [x] 5.1 Add `result_repeated: true` to the `stall_detected` event data, keeping
      `tool`, `repeat_count`, `limit`, and `turn_id`.
- [x] 5.2 Add a `stall_nudge` event (`tool`, `repeat_count`, `limit`, `turn_id`) with
      no accompanying `error` event, since the run continues.

## 6. Tests

- [x] 6.1 Update the existing stall-guard tests in `task-runner/test_main.py` for the
      three-argument `record()` signature and the new default of 3:
      `test_stall_detector_trips_on_identical_repeats`,
      `test_stall_detector_argument_order_insensitive`,
      `test_stall_detector_distinguishes_by_tool_and_args`,
      `test_stall_detector_disabled_when_limit_non_positive`,
      `test_stall_detector_handles_unserializable_args`,
      `test_stall_detector_reproduces_blog_to_tweets_loop`.
- [x] 6.2 Add a regression test for the false positive: identical `execute_command`
      arguments returning `weighted_chars: 207` → `184` → `174` must not trip, at any
      repeat count.
- [x] 6.3 Add a regression test for the real stall: identical `write_file` arguments
      returning `"Wrote 354 bytes to /tmp/tweet.md"` trips at exactly the limit.
- [x] 6.4 Add a test that a later recurrence of an earlier result does not accumulate
      (A → B → A leaves the counter at 1).
- [x] 6.5 Add a test that interleaved repeating keys each accrue independently and
      trip.
- [x] 6.6 Add a test that two long results identical up to the truncation length but
      differing after it produce different digests and do not trip.
- [x] 6.7 Add a test that a call with no recorded output leaves counters and digests
      untouched (a tool that raises never reaches its output guardrail).
- [x] 6.8 Add a test that the guardrail is attached to every tool returned by the
      overridden `get_all_tools()`, including MCP-derived `FunctionTool`s, and that
      calling it twice does not attach duplicates.
- [x] 6.9 Add nudge-tier tests: nudge fires at `STALL_NUDGE_LIMIT` and the run
      continues; a nudged key that keeps looping still aborts at
      `STALL_REPEAT_LIMIT`; a key is nudged at most once per attempt; the nudge does
      not reset any counter; a fresh attempt clears nudge state.
- [x] 6.10 Add config tests: `STALL_NUDGE_LIMIT <= 0` disables only the nudge;
      `STALL_REPEAT_LIMIT <= 0` disables both tiers; `STALL_NUDGE_LIMIT >=
      STALL_REPEAT_LIMIT` disables the nudge with a warning rather than reordering.
- [x] 6.11 Add an event test: a nudge emits `stall_nudge` with no `error`, and a
      nudge-then-abort run emits `stall_nudge` followed by `stall_detected` + `error`.
- [x] 6.12 Run the full task-runner suite and confirm no unrelated regressions.

## 7. Verify and ship

- [x] 7.0 Verify the wiring against the **real** SDK, not the conftest mocks — the
      mocks could hide an incompatibility in exactly the seam this change depends on.
      *Confirmed: `main` imports cleanly with the real `agents` package;
      `AgentStallError` is an `AgentsException`; `make_stall_guardrail` returns a real
      `ToolOutputGuardrail`; `GuardedAgent` subclasses `Agent` with an async
      `get_all_tools`. Driving the guardrail with real `ToolContext` /
      `ToolOutputGuardrailData` objects produced exactly the specified sequence:
      allow, allow, reject_content + `stall_nudge`, allow, allow, then
      `AgentStallError` + `stall_detected` at 6. Also traced the SDK to confirm the
      overridden `get_all_tools` is on the execution path — `run_internal/run_loop.py:669`
      (the streamed path) feeds its result into the turn, carrying the guardrails.*
- [x] 7.1 Run the stack locally with `docker compose -f testing/docker-compose.yml up
      --build` and exercise a task that repeats an identical call with a changing
      result; confirm it is no longer aborted.
      *Both images build; postgres, migrations and the errand server come up and the
      health endpoint responds. The new code was exercised inside the built
      `errand-task-runner:latest` image (correct defaults, changing result → `[1,1,1]`,
      identical result → `[1..6]`). **Not** driven as a queued task through the local
      stack: LLM credentials live in the `settings` table and a fresh local database
      has none, so that path would have required configuring credentials in the local
      app. The changing-result case is covered by unit tests, the guardrail tests, and
      the in-image check instead. Host port 5432 was already taken by an unrelated SSH
      tunnel and container, so postgres was published on 5433 via a scratchpad-only
      compose override — no repo change.*
- [x] 7.2 Exercise a genuinely looping task and confirm it is nudged at 3 with a
      `stall_nudge` event, and that if it keeps looping it aborts at 6 with
      `stall_detected` carrying `result_repeated: true`.
      *Nudge verified **live**: `main.py`'s own `GuardedAgent` and
      `make_stall_guardrail` were driven through a real `Runner.run` against
      `google/gemma-4-26b-a4b`, with a tool returning a constant result. The model
      called `write_file` three times identically, the guardrail fired, emitted
      `stall_nudge`, and the model stopped repeating. This is the one seam the
      isolated tests could not cover — that the `get_all_tools()` attachment survives
      the SDK's real tool pipeline. The abort at 6 is verified against real SDK types
      (allow, allow, reject_content, allow, allow, `AgentStallError` +
      `stall_detected` with `result_repeated: true`) but not in a live model run,
      because the nudge stopped the loop before it got there — the desired outcome.*
- [x] 7.3 Push the branch and open a PR. *PR #224.*
- [ ] 7.4 Confirm CI builds images and the Helm chart, then validate the built
      artifacts deploy cleanly on Kubernetes before merging.
- [ ] 7.5 After deploy, re-check Grafana Loki for `stall_detected` events on task
      `8cfb051a` to confirm the guard's new behaviour in production.
