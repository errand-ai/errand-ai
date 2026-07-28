## Context

`StallDetector` (`task-runner/main.py`) currently keys on `(tool, canonical_args)`
and increments a per-signature counter that never decreases for the lifetime of an
agent attempt. The counter is incremented in the streaming loop at
`event.name == "tool_called"` — i.e. **before the tool has run**, so the result is
not available at the decision point.

Two production transcripts of task `8cfb051a` (2026-07-27, `gemma-4-26b-a4b-it-mlx`)
establish the discriminating signal:

| Call | Arguments | Results | Verdict |
|---|---|---|---|
| `execute_command count_tweet_chars.py /tmp/tweet.md` ×3 | identical | `207` → `184` → `174` | healthy iteration |
| `write_file /tmp/tweet.md` ×6 | identical | `Wrote 354 bytes` ×6 | genuine stall |

Identical arguments alone cannot separate these. Identical arguments **plus an
unchanged result** can. Since `parse_queue.py` requests up to 10 blog entries and the
verify loop runs ~3 identical `count_tweet_chars` calls per entry, the current rule
aborts a healthy two-entry run.

Relevant SDK facts, confirmed against `agents/items.py` in
`task-runner/.venv`:

- `ToolCallItem.raw_item` carries `call_id`.
- `ToolCallOutputItem.raw_item` is a dict containing `call_id`, and the item exposes
  the return value as `.output`.

So a call can be paired with its own output by `call_id`, which is correct even when
the model emits several tool calls in one turn and they resolve out of order.

## Goals / Non-Goals

**Goals:**

- Stop counting a repeat when the tool's result changed — that is progress.
- Stop letting repeats accrue across a key's own history when the result changed in
  between, so an incidental later recurrence cannot creep toward the limit.
- Intervene earlier *without* killing the run: give the agent a chance to finish
  before the hard abort takes its work away.
- Keep the transcript legible: an operator should be able to tell from
  `stall_detected` / `stall_nudge` that the result was unchanged, not merely the
  arguments.

**Non-Goals:**

- Salvaging partial work when a stall does abort (`result: ""` behaviour is
  unchanged).
- Reducing system-prompt / tool-catalog context load. The spike found this is a
  *larger* lever on stall rate than the nudge, but it is a different change.
- Detecting multi-step cycles that never repeat a single call (e.g. a strict
  A→B→A→B alternation where both results change every time).
- Changing retry semantics: a stall abort remains non-retryable.

## Decisions

### D1: Signature includes a digest of the tool result

The counted key stays `(tool, canonical_args)`. What changes is that each key stores
the **digest of the result its last invocation returned**, and a repeat only accrues
when the new invocation returns the same digest.

*Why a digest and not the result itself:* results are unbounded (`read_url` returns a
whole article). Storing one digest per key keeps memory flat regardless of payload
size.

*Why hash the full result, not the truncated form:* `_truncate` is already applied for
the `tool_result` event. Hashing the truncated string would let two long, different
outputs that share a prefix collide into a false stall. Hash `str(result)` in full.

*Alternative rejected — fold the result into the signature string* (making
`(tool, args, result)` one key). That makes each distinct result its own counter,
which fixes the `count_tweet_chars` case, but leaves a creep path: if entry 5's tweet
coincidentally weighs the same as entry 2's, those two non-adjacent invocations share
a key and accrue together. Storing the digest *against the key* and resetting on
change closes that.

### D2: Accrual is consecutive within a key's own call sequence

For key `k`, the counter counts invocations of `k` that returned the same digest as
the immediately preceding invocation **of `k`**. A different digest resets `k`'s
counter to 1. Interleaved calls to *other* keys do not reset `k`.

*Why not strict global adjacency* (a single `last_signature` + run length): it is
simpler, but an interleaved loop — the agent alternating `write_file` and `read_file`
forever, each returning the same thing — would reset both counters on every call and
never trip. Both observed stalls were globally consecutive, but the original gemma
`/tmp/blogs.work.md` loop that motivated the guard was not necessarily. Per-key
consecutiveness catches interleaved loops while still discarding the
`count_tweet_chars` false positive, because there the *result* changes.

| Rule | `count_tweet_chars` 207/184/174 | `write_file` 354 ×6 | interleaved A,B,A,B (results fixed) |
|---|---|---|---|
| Today: cumulative, args only | accrues ✗ | trips ✓ | trips ✓ |
| Global adjacency | resets ✓ | trips ✓ | never trips ✗ |
| **Per-key consecutive + digest** | resets ✓ | trips ✓ | trips ✓ |

### D3: Record from a `ToolOutputGuardrail`, not the streaming loop

The detector moves out of the stream-event handler entirely and into a
`ToolOutputGuardrail` attached to every tool. `ToolOutputGuardrailData` supplies
`context.tool_name`, `context.tool_arguments`, and `output` — the complete detector
input in a single callback, already correlated, with no pending-call bookkeeping.

*Why not the streaming loop.* The obvious alternative is to stash `(tool, args)` at
the `tool_called` event and pop it at `tool_call_output_item`, pairing by `call_id`.
That works for this change in isolation, but it is the wrong seam for two reasons:

1. **It counts the wrong value once a nudge exists.** The sibling change
   `stall-guard-soft-nudge` delivers its nudge via
   `ToolGuardrailFunctionOutput.reject_content(...)`, which replaces `final_result`
   with the nudge message — and `final_result` is exactly what
   `ToolCallOutputItem.output` carries. A stream-based detector would hash the nudge,
   see a changed digest, and reset the counter, then hash the real result next call
   and reset again, oscillating forever without ever reaching the abort. The
   guardrail sees `real_result` *before* substitution
   (`run_internal/tool_execution.py:1307-1330`), so the counter keeps accruing while
   the model sees the nudge. The "nudging never resets the count" rule that change
   requires is unimplementable in the stream design and free here.
2. **It would be built twice.** Adopting the guardrail now means the nudge tier is a
   branch inside an existing callback rather than a relocation of the whole detector.

*Attachment.* `tool_output_guardrails` is a field on `FunctionTool` (`tool.py:250`),
and MCP tools are constructed without it (`mcp/util.py:304`). Override
`Agent.get_all_tools()` (`agent.py:193`), which returns native and MCP tools
together, and attach the guardrail to every `FunctionTool` in the returned list. The
override must be idempotent — it is invoked per turn.

*Consequence:* the offending call executes before the guard fires, where previously
the abort pre-empted it. Acceptable precisely because of what the guard now tests: we
only abort when the result was identical to last time, so the extra execution is by
construction a no-op.

*Transcript trade-off.* An earlier draft of this section claimed the change
*strengthens* transcript visibility because both `tool_call` and `tool_result` would
precede the abort. That is wrong, and code review caught it. The SDK runs tool output
guardrails at `run_internal/tool_execution.py:902`, *before* `hooks.on_tool_end` at
line 911 — and `on_tool_end` is the sole site that emits `tool_result`
(`main.py:443`). Raising `AgentStallError` from the guardrail therefore skips
`on_tool_end`, so the aborting call emits `tool_call` but never `tool_result`.

Accepted rather than worked around. The original intent — the offending call stays
visible — still holds via `tool_call`, the repeated result is already in the
transcript from the preceding identical calls, and `stall_detected` carries
`result_repeated`. Emitting `tool_result` from inside the guardrail would duplicate
the hook's logic for no diagnostic gain.

Note the asymmetry: a *nudged* call returns normally, so `on_tool_end` does run and
its `tool_result` is emitted — carrying the nudge message rather than the tool's real
output, as recorded in the audit section.

*Edge case, now resolved by construction:* a call that never returns (tool raised,
run torn down) never reaches its output guardrail, so it is simply never recorded.
No pending-call map to leak.

### D4: Two tiers — nudge at 3, abort stays at 6

Higher precision argues for a hair trigger, and an earlier draft of this design
lowered `STALL_REPEAT_LIMIT` from 6 to 3 on that basis. Folding in the soft-fail work
makes that wrong: with a nudge firing at 3, aborting at 3 would pre-empt the very
intervention meant to rescue the run.

So the early response becomes soft, and the hard limit does not move:

| | env var | default | behaviour |
|---|---|---|---|
| nudge | `STALL_NUDGE_LIMIT` | 3 | replace the tool result with a message, continue |
| abort | `STALL_REPEAT_LIMIT` | 6 (unchanged) | `stall_detected`, fail as `stalled`, no retry |

`STALL_REPEAT_LIMIT <= 0` continues to disable the guard entirely.
`STALL_NUDGE_LIMIT <= 0` disables only the nudge tier, leaving the abort intact. A
nudge value at or above the abort value means the nudge can never fire; treat it as
disabled and log a warning rather than silently reordering the tiers.

This also removes an interim-state problem that splitting the work would have
created: shipping the precision fix alone at a limit of 3 would have made the guard
strictly more aggressive than today, with no soft landing underneath it.

### D5: Nudge wording targets `submit_result`, not "try something else"

The spike (see the audit section) measured *which* transition the nudge causes. It
does **not** significantly reduce identical repeats (13% → 7%, p=0.36). What collapses
is dithering: `count_tweet_chars` calls fall 24/60 → 2/60 while `submit_result` rises
47% → 90%. The nudge converts *dithering into completion*.

That is exactly the observed production failure — a finished tweet the model kept
fiddling with — so the message must name the escape hatch:

> You have called `<tool>` N times with identical arguments and got the same result
> every time; the effect is already in place. If your work is complete, call
> `submit_result` now with a summary. If it is not, do something different.

A generic "vary your approach" would target the repeat rate, which is the thing the
evidence says the nudge does *not* move.

### D6: Bounding the nudge

A signature is nudged at most once per attempt, and nudging never resets its counter.
Both rules are required for termination: without the first, an agent that ignores the
nudge is nudged on every subsequent call; without the second, the counter never
reaches the abort.

Recording the *pre-substitution* result (D3) is what makes the second rule possible at
all — see the oscillation failure described there.

### D5: `stall_detected` gains a result-identity field

Add `result_repeated: true` (and keep `repeat_count`, `limit`, `tool`, `turn_id`) so
the transcript distinguishes "same input, same output" from the older args-only
semantics. Operators reading historical transcripts can then tell which rule was in
force.

## Risks / Trade-offs

- **The nudge is a probability shift, not a fix.** It lifts the escape rate to ~90%,
  not 100%, and does not significantly reduce identical repeats. Roughly one nudged
  run in ten still reaches the abort. → Accepted; the abort backstop remains. Do not
  describe this feature as preventing stalls.
- **Nudging at 3 interrupts an agent that was about to recover unaided.** The control
  arm escaped 47% of the time with no intervention, so some nudges land on runs that
  did not need one. → The nudge is additive information, not a redirect away from a
  chosen path, and the measured net effect is strongly positive. `STALL_NUDGE_LIMIT`
  tunes it without a redeploy.
- **The nudge message is attacker-adjacent input to the model.** It is injected as a
  tool result, the same channel a compromised tool would use. → The text is a fixed
  template with only the tool name and a count interpolated; no tool-supplied content
  is echoed into it.
- **Repeated identical tool *failures* now trip the guard** (e.g. `read_url` returning
  the same error three times consecutively). → Arguably correct — retrying an
  identical call for an identical error is not progress — but it interacts with the
  existing retry/classification machinery. Verify the error path still classifies
  before the stall guard sees a third identical failure.
- **Non-deterministic results mask real stalls.** A tool whose output embeds a
  timestamp never repeats a digest, so a loop on it never trips. → The guard is a
  backstop, not the only one; `MAX_TURNS` still bounds the run. Accepted; the audit
  below enumerates the currently-blind tools.
- **Side effects invisible to stdout produce a false positive the result rule does
  not catch.** The harness surfaces only stdout as the tool result, and
  `execute_command` renders an empty stdout as the constant `"(no output)"`. A
  state-advancing command invoked with identical arguments — say
  `python3 advance_queue.py`, stepping through entries and printing nothing — returns
  `"(no output)"` every time while making real progress, and now aborts at 3. This is
  the exact mirror of the `count_tweet_chars` case: there the arguments repeat and the
  result moves; here the result repeats and the *state* moves. → No fix inside the
  detector; the signal genuinely is not there. Mitigations are `STALL_REPEAT_LIMIT`
  and authoring skills so that progress-bearing commands print something. Worth
  checking existing skill scripts for identical-args/silent-stdout loops before
  lowering the default to 3.
- **Digest collisions.** → Use SHA-256 over the full result string; collision risk is
  not a practical concern.
- **Existing tests encode the old rule.** `test_stall_detector_trips_on_identical_repeats`,
  `..._distinguishes_by_tool_and_args`, `..._reproduces_blog_to_tweets_loop` and the
  disabled/unserializable cases all call `record(tool, args)` with a two-argument
  signature and assume cumulative counting. → `record()` gains a result parameter;
  these tests must be rewritten as part of the change, not left to drift.

## Migration Plan

No data migration. Behaviour-only change inside the task-runner image.

- Deploy is the normal task-runner image build; no Helm or DB change.
- Rollback: set `STALL_REPEAT_LIMIT=0` to disable the guard entirely without a
  redeploy, or roll the image back.
- Operators who have pinned `STALL_REPEAT_LIMIT` see no threshold change, only the
  narrower trigger condition.

## Audit: is `str(result)` stable? (resolves task 2.1)

Audited 2026-07-27 against production task-runner logs in Loki (7-day window,
~75k `tool_result` lines, 20 distinct tools) and the vendored SDK in
`task-runner/.venv`.

**The evidence is valid for this question.** `run_internal/tool_execution.py`
sets `result = final_result` and passes the *same object* to both
`hooks.on_tool_end(..., final_result)` (line 911) and
`ToolCallOutputItem(output=result)` (line 978). The transcript's `output` field is
therefore derived from exactly the object the guard will hash.

One precision, given D3: the guardrail hashes `real_result`, while the transcript
logs `final_result`. With no guardrail performing substitution these are the same
object, so the audit holds exactly for this change. Once `stall-guard-soft-nudge`
lands, a nudged call will log the *nudge message* as its `tool_result` while the
detector hashed the real output — future log-based audits must not read the two as
interchangeable.

Findings:

- **No object reprs or memory addresses anywhere.** A 7-day scan for `at 0x`,
  `object at`, `CallToolResult`, `TextContent(`, `meta=None` returned zero hits.
- **`duration_ms` is a sibling field of `output`, not part of it.** Per-call timing
  does not pollute the digest — the single most likely way this design could have
  failed silently.
- **MCP tool results are dicts, not strings.** They render as
  `{'type': 'text', 'text': '...'}`, so `str(result)` is a dict repr. Deterministic
  today (insertion-ordered, no addresses), but it means `str()` is load-bearing: an
  MCP result carrying multiple content blocks, or any change in key construction
  order, changes the digest. Native tools return plain strings.
- **`discover_tools` is fully deterministic on repeat.** `tool_registry.py:185-228`
  classifies against `all_known_tools`, not against `enabled_tools`, so re-enabling
  an already-enabled tool reports `Enabled: …` again rather than switching to
  `Already enabled`. Output ordering follows the caller's argument order, with no set
  iteration. A re-`discover_tools` loop — one of the guard's original motivating
  cases — therefore produces identical digests and trips at exactly the limit, with
  no delay.
- **Permanently blind tools** (digest can never repeat, so the guard degrades to
  "never trips"): `retain` returns a fresh `operation_id` UUID per call;
  `query_loki_logs` embeds timestamps; `web_search` and `browser_navigate` return
  live content. Accepted — `MAX_TURNS` remains the backstop for these.
- **The false positive is confirmed, not hypothetical.** Pod
  `task-runner-65160b3f-72hmw` (task `6f70c60f`, 2026-07-26 10:00 UTC) issued
  `execute_command python3 …/count_tweet_chars.py /tmp/tweet.md` with byte-identical
  arguments **five times** in one healthy drafting run — one short of the current
  limit of 6. Under the rule in this change all five reset, because each returned a
  different character count.

### Steerability spike (resolves the nudge tier's gating question)

Run 2026-07-27 against `google/gemma-4-26b-a4b` on a local LM Studio endpoint. The
production loop state was seeded directly — five byte-identical `write_file` calls
after a draft had already measured 174 of 280 weighted characters — and only the
final tool result was varied: the real result (control) versus the nudge message
(treatment). One completion per rep, classified by the next action.

| | control | treatment | Fisher p |
|---|---|---|---|
| escaped to `submit_result` | 28/60 (47%) | 54/60 (90%) | <0.000001 |
| kept repeating identically | 8/60 (13%) | 4/60 (7%) | 0.36 (n.s.) |

Pooled with an earlier 30-per-arm run: 44/90 → 78/90, p=7×10⁻⁸.

Two results shaped the design rather than merely approving it:

- The nudge moves *dithering*, not repetition — `count_tweet_chars` fell 24/60 → 2/60
  while the repeat rate barely moved. Hence D5's wording.
- **The loop only reproduces under context load.** With three tools and a two-line
  system prompt the model escaped 8/8 with no nudge at all; only a production-scale
  prompt plus a ~45-entry tool catalog dropped it to ~47%. Context load is a bigger
  lever than the nudge and belongs in its own change.

Method caveats worth carrying forward: two earlier spike designs each produced a
confident but meaningless verdict — the first never reproduced a loop, the second had
a control arm that escaped 8/8, leaving no signal to measure. Always confirm the
control reproduces the failure before believing a treatment effect. The spike also ran
against LM Studio directly, whereas production goes through LiteLLM; if the malformed
`<|channel|>thought` markers originate in that layer they remain unexplained.

Audit limitations: transcript `output` is truncated at `TOOL_RESULT_MAX_LENGTH`
(500 chars), so nondeterminism beyond the first 500 characters of a long result is
invisible to this method. The guard hashes the untruncated string, so a tool with a
trailing timestamp would be blind in production while looking clean here.

## Open Questions

- Does overriding `Agent.get_all_tools()` interact with the existing
  `ToolFilterCallable` / lazy tool-visibility machinery? Both touch the per-turn tool
  list; confirm attaching guardrails does not disturb which tools the model sees.
- Should tools known to be permanently blind (`retain`, `query_loki_logs`,
  `web_search`, `browser_navigate`) be recorded at all, or skipped explicitly so the
  blindness is declared in code rather than emergent? Skipping costs nothing and
  makes the limitation greppable.
