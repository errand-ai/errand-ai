## Why

The stall guard shipped in `task-runner-stall-guard` has two problems, both confirmed
against production transcripts of the `Process Blog URLs Twitter Posts` task
(`8cfb051a`, 2026-07-27, `gemma-4-26b-a4b-it-mlx`).

**It fires on healthy work.** The signature is `(tool, args)`, counted cumulatively
across an agent attempt and blind to the tool's result. A *healthy* draft-and-verify
iteration called

```
execute_command  python3 .../count_tweet_chars.py /tmp/tweet.md
```

with byte-identical arguments three times per blog entry, returning
`weighted_chars: 207`, then `184`, then `174`. Different results each time — progress,
not a stall. The queue parser requests up to 10 entries; a healthy run in pod
`task-runner-65160b3f-72hmw` already reached **five** identical calls, one short of
the limit. What separates this from a real stall is the *result*: the genuine loop was
six consecutive `write_file` calls with identical arguments **and** identical results
(`"Wrote 354 bytes to /tmp/tweet.md"` ×6).

**Its only response is to destroy completed work.** In the observed run the agent had
already drafted the tweet and verified it at 174 of 280 weighted characters. The
deliverable was finished and on disk. It then rewrote the identical file six times
without calling `submit_result`, and the guard aborted with
`{"status": "failed", "result": ""}`. The failure is not "cannot make progress" but
**"has finished and cannot stop"** — and a hard abort is the wrong first response to
that.

A steerability spike (2026-07-27, `google/gemma-4-26b-a4b`, seeded loop state,
n=60/arm) shows an in-band nudge fixes it: escape to `submit_result` rises from
28/60 (47%) to 54/60 (90%), Fisher p<0.000001; pooled with a 30/arm run, 44/90 →
78/90, p=7×10⁻⁸.

## What Changes

**Precision — stop counting healthy iteration:**

- Extend the counted state from `(tool, args)` to `(tool, args)` keyed against a
  digest of the result that key last returned. A repeat accrues only when the result
  is unchanged; a differing result resets the counter to 1.
- Interleaved calls to *other* keys do not reset a key's counter, so a loop that
  alternates between two repeating calls is still caught.

**Soft-fail — stop destroying finished work:**

- Add a nudge tier at a new `STALL_NUDGE_LIMIT` (default 3). On reaching it, the
  runner replaces the tool result with a message stating that the call has repeated
  with no change in result, that its effect is already in place, and that the agent
  should call `submit_result` if the work is complete.
- `STALL_REPEAT_LIMIT` (default **unchanged at 6**) remains the hard-abort backstop.
  With a soft intervention at 3, lowering the abort would be self-defeating.
- A signature already nudged is not nudged again, and nudging never resets the count,
  so a nudged-but-still-looping agent still reaches the abort.

**Mechanism (both tiers):**

- Site the detector in a `ToolOutputGuardrail` rather than the streaming loop.
  `ToolGuardrailFunctionOutput.reject_content(...)` delivers the nudge and continues
  execution; the guardrail observes the *pre-substitution* result, which is what makes
  the "nudging never resets the count" rule implementable at all.
- Emit `stall_nudge` on a soft intervention and keep `stall_detected` for the abort.

Not in scope: salvaging partial work when a stall does abort (`result: ""` is
unchanged), and reducing the system-prompt/tool-catalog context load — see Impact.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `task-runner-error-resilience`: the "No-progress loop detection (stall guard)"
  requirement changes its signature definition (adds the result), its accrual rule
  (cumulative → consecutive per key), and gains the soft-nudge tier and
  `STALL_NUDGE_LIMIT`.
- `structured-task-events`: `stall_detected` gains a field recording that the result
  was unchanged; a new `stall_nudge` event covers soft interventions.

## Impact

- `task-runner/main.py` — `StallDetector`, `DEFAULT_STALL_REPEAT_LIMIT`, a new
  `DEFAULT_STALL_NUDGE_LIMIT`, removal of the stream-loop recording site, a new
  `ToolOutputGuardrail`, and an agent subclass overriding `get_all_tools()` so MCP
  tools are covered (`mcp/util.py:304` builds them without guardrails).
- `task-runner/test_main.py` — the six existing stall-guard tests assume a
  two-argument `record()` and cumulative counting; they are rewritten here, not left
  to drift.
- Operators who have pinned `STALL_REPEAT_LIMIT` see no threshold change, only a
  narrower trigger condition plus a soft tier ahead of it.
- No API, database, or Helm changes.
- **Related but deliberately excluded:** the spike found the loop only reproduces
  under context load — with three tools and a short system prompt the model escaped
  8/8 unprompted, while a production-scale prompt and ~45-entry tool catalog dropped
  it to ~47%. Context load is a larger effect than the nudge and warrants its own
  change; it is not addressed here.
