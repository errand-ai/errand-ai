## Context

`fix-context-compaction` made compaction work. Production immediately showed it working repeatedly — four compactions in 104 seconds on one task, each re-summarising the same 49 messages while the input grew from 53 to 65. Real calls took 28s and 30s; the two that returned in ~24ms were LiteLLM cache hits on a near-identical prompt and will stop helping once content shifts.

The cause is architectural and confirmed from the SDK source: `call_model_input_filter` is a per-call transform. The run loop rebuilds history from its own items after every turn (`streamed_result._model_input_items = turn_result.pre_step_items + turn_result.new_step_items`), and the filter's output is never written back. Sessions do not help — `prepare_input_with_session` is called once before the turn loop, so a mid-run session rewrite changes what is stored, not what the current run sends. Maintainers have declined to build a provider-agnostic equivalent, and issue #2671 acknowledges the gap.

So per-turn recomputation is inherent to the supported hook. What is not inherent is *re-summarising the same messages*.

Two further facts shape the work:

- **`Iterative compaction via summary merging` is specified but cannot execute.** `MERGE_COMPACTION_PROMPT` and `_is_compaction_summary()` detect a prior summary by looking for `COMPACTION_SUMMARY_PREFIX` *in the messages*. Since the compacted list never persists, no later compaction ever sees one. Every compaction takes the first-compaction path.
- **The split point can orphan a tool call from its result.** It is chosen purely by accumulating tokens backwards, with no pairing check. Cline, OpenHands, LangChain and strix all guard this; errand does not.

## Goals / Non-Goals

**Goals:**

- A compaction split never separates a `function_call` from its `function_call_output`.
- Repeated compactions summarise only what is new, not the whole prefix again.
- The existing merge requirement becomes reachable rather than remaining specified-but-dead.
- Whether a compaction merged or re-summarised is visible in logs.

**Non-Goals:**

- Making compaction persist across turns. The SDK does not support it; see Context.
- The overflow-retry architecture used by strix, koder and Datus — compact between runs and restart `Runner` with the compacted history. It is the only approach that makes compaction genuinely persist, and errand is closer to it than expected since it already retries around `Runner.run_streamed()`. It is a restructuring of the runner's control flow and wants its own change.
- Evicting reconstructible tool outputs before summarising (the Manus "compact then summarise" tiering, and `agents.extensions.ToolOutputTrimmer`). Likely higher value than anything here, since errand's context is dominated by large file reads — but separate.
- Changing `KEEP_RECENT_TOKENS`. Research settled it: 20,000 is the convergent constant across Cline and Codex.

## Decisions

**Fix the split point first, and treat it as independent.** It is the only item here that can fail a live task rather than merely cost time, and its fix is small and well-precedented. Sequencing it first means the risky part of this change (chained summaries) cannot delay it, and if the rest is deferred the bug is still gone.

**Snap the split forward to the next safe boundary, not backward.** Moving the boundary later keeps *more* in the summarised portion and less in the retained tail, which errs toward reclaiming more context. Moving it earlier would retain a larger tail and could leave the conversation over the threshold after a compaction that appeared to succeed — a silent failure, versus a slightly deeper cut which is merely lossy. Both directions preserve pairing; only one degrades safely.

**Hold the previous summary in errand's own state rather than reading it back from the messages.** The existing merge detection assumes the summary is in the history, which is precisely what the SDK does not do. A module-level record — the summary text plus a digest of exactly what it covered — sits alongside `_compaction_backoff`, resets on the same per-attempt boundary, and makes the merge path work without fighting the framework. This mirrors what Cline does with `findLatestSummaryIndex()`, adapted to a history we do not own.

**Key the record on content, not on message count or index.** Indices shift as the SDK rebuilds the list; a count says nothing about identity. A digest over the serialised content of the messages a summary covered is the only thing that safely answers "does this summary still describe that prefix?". Getting this wrong is the change's main hazard: a stale summary spliced in front of unrelated messages misrepresents history silently, which is worse than recomputing.

**Fall back to a full re-summarisation whenever the record does not match.** Any doubt — digest mismatch, missing record, backoff reset — takes the first-compaction path. Correctness over savings: the failure mode of an unnecessary re-summarisation is 30 seconds, the failure mode of a wrong merge is a model working from a false account of its own history.

**Log merge-versus-full at `WARNING`.** Consistent with the lifecycle logging already in place, and for the same reason: production runs above `INFO`. Without it, "did chaining actually engage?" is answerable only by timing inference, which is exactly the position that made the original defect invisible for weeks.

## Risks / Trade-offs

**A stale or mismatched summary silently misrepresents history** → The central risk. Mitigated by content digests and by falling back to full re-summarisation on any mismatch, but it is a correctness risk introduced in exchange for a latency saving, and worth weighing on that basis.

**`MERGE_COMPACTION_PROMPT` has never executed** → It is specified, tested only in unit tests against synthetic input, and has produced no output in production. Switching it on is shipping unproven code, not enabling existing behaviour. It should be reviewed and tested as new.

**Snapping the split changes how much is retained** → Moving the boundary forward cuts deeper than `KEEP_RECENT_TOKENS` implies. Usually marginal, but a single very large tool result could move it a long way and discard more recent context than intended.

**Collision with `pin-constraints-across-compaction`** → Both edit the split. That change excludes `messages[0]` from summarisation; this one constrains where the boundary may fall. Compatible in principle, conflicting in practice if developed in parallel.

**Screenshot-heavy tasks will not benefit** → Found during implementation. `_strip_screenshots` runs ahead of `_compact_context` on every turn and replaces the *oldest* screenshots once more than `MAX_RETAINED_SCREENSHOTS` exist. Which images qualify shifts as new ones arrive, so a message inside the covered prefix can be rewritten between compactions. The digest then disagrees and the merge falls back to a full summarisation — correct, but the saving is lost precisely in the tasks whose context grows fastest. Making the digest ignore screenshot placeholders would recover it, at the cost of a digest that no longer covers the full content. Not attempted here.

**Merging drifts** → Each merge summarises a summary. Over many compactions detail erodes in ways a single full summarisation would not. Cline and OpenHands both accept this, and it is the standard trade, but a very long task may end up working from a summary several generations removed from events.

## Migration Plan

No schema, settings or data change. Behaviour changes only for tasks that compact more than once.

Rollback is a version revert; the state is in-process and nothing persists.

Ordering against `pin-constraints-across-compaction` matters more than deployment. Whichever lands second must rebase onto the first. The split fix here is the more urgent of the two, which argues for this change first — but that is a judgement call, not a constraint.

## Open Questions

- Should the summary record survive an agent retry rather than resetting per attempt? Resetting matches `_compaction_backoff` and is the conservative choice, but a retry restarts from the original prompt and may re-cover the same ground, so a surviving summary could be valid. Needs care: "may be valid" is not "is valid".
- How many generations of merge before quality degrades enough to warrant a full re-summarisation? No published guidance found. A generation counter with a forced full pass every N is easy to add if it proves necessary.
- Should the split-point fix be pulled into its own change and shipped ahead of the rest? It is the only item that can fail a live task, and it is independent of everything else here.
