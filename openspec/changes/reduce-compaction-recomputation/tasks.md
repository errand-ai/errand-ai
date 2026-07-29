## 1. Branch and sequencing

- [x] 1.1 Create branch `reduce-compaction-recomputation`
- [x] 1.2 Bump `VERSION` (minor — behaviour change to compaction) — `0.142.0` → `0.143.0`
- [x] 1.3 Settle the order against `pin-constraints-across-compaction` and record it in both changes. Both edit the split in `_compact_context` — that one excludes `messages[0]` from summarisation, this one constrains where the boundary may fall. Compatible in principle, conflicting if developed in parallel — **decided: this change lands first.** The split-point bug can orphan a `function_call` from its `function_call_output` and fail a live task; `pin-constraints` costs safety margin but is not actively breaking runs. Recorded in `pin-constraints-across-compaction/tasks.md` §2, which now rebases onto this
- [x] 1.4 Note the branch dependency: this branch is cut from `pin-constraints-across-compaction`, because the archive/sync of `fix-context-compaction` lives there and `main`'s specs are stale without it. Either merge that first, or rebase this onto `main` once it lands — **resolved**: PR #236 merged as `dff635e` (squash), carrying both the `fix-context-compaction` archive and the `pin-constraints-across-compaction` artifacts. This branch was reconstructed from `main` (the squash made a plain rebase replay commits already present). `main`'s `task-runner-context-compaction` spec now holds all 8 synced requirements, so this change's `MODIFIED` delta targets live text

## 2. Split-point safety — do this first

The only item here that can fail a live task rather than merely cost time. Independent of everything else, so it should not wait on the riskier work below.

- [x] 2.1 Write failing tests first: a boundary falling between a `function_call` and its `function_call_output` is moved; the retained portion never begins with an orphaned output; a boundary already at a safe point is left unchanged — 7 tests in `tests/test_compaction.py`. First draft of the two end-to-end tests **passed against a no-op stub**, i.e. they proved nothing: a small `function_call` fits inside `KEEP_RECENT_TOKENS` alongside its output, so the boundary never landed between them. Rebuilt around `_messages_splitting_on_a_tool_pair()`, whose ~1,340-token call arguments force the boundary onto the pair
- [x] 2.2 Write a failing test for the degenerate case — moving forward past a very large tool pair retains less than `KEEP_RECENT_TOKENS`, and compaction proceeds anyway — `test_compaction_proceeds_when_snapping_retains_less_than_keep_recent`: snapping leaves only the ~16-token tail, and compaction still runs
- [x] 2.3 Move the boundary **forward**, not backward — `_snap_split_forward()`. Advances past `function_call_output` items at the head of the retained portion. A type check suffices: calls precede their outputs, so an output at that position is orphaned by construction — no `call_id` lookup, which matters because the id is absent on some reconstructed history
- [x] 2.4 Confirm this composes with the existing "at least one summarised, at least one kept" clamp — snapping runs *after* the clamp and stops at `len(messages) - 1`, so the guarantee holds. `test_split_forward_stops_before_consuming_every_message` pins it
- [x] 2.5 Consider whether to ship this alone, ahead of the rest — kept shippable rather than decided in advance: section 2 is committed on its own, touching only `_snap_split_forward` and four lines of `_compact_context`, so it can be cherry-picked out if the chained-summary work below proves troublesome. Deciding now would have been premature; making the decision reversible costs nothing

## 3. Summary state

- [x] 3.1 Write failing tests first: a held summary matching the messages triggers the merge prompt; only messages beyond the covered prefix are sent; a content mismatch falls back to a full summarisation; no held summary falls back to a full summarisation
- [x] 3.2 Write a failing test that the held summary is cleared on agent retry, as `_compaction_backoff` is
- [x] 3.3 Add the summary record alongside `_compaction_backoff` — `_compaction_summary` holds the summary text, a digest of what it covered, and the prefix length; `_reset_compaction_summary()` is called next to `_reset_compaction_backoff()` per agent attempt
- [x] 3.4 Key the record on **content**, not index or message count — SHA-256 over the serialised covered prefix. `covered_count` is stored but is only a slicing hint; it is never trusted until the digest agrees, so a tampered message at the same position cannot pass
- [x] 3.5 Fall back to full summarisation on any doubt — mismatch, missing record, post-reset. `_match_held_summary` returns `None` on each and the caller takes the first-compaction path

## 4. Make the merge path live

- [x] 4.1 Route to `MERGE_COMPACTION_PROMPT` when a held summary matches — the held record is checked first; the `_is_compaction_summary` marker path is retained beneath it for the case where a summary message does reach the history by some other route, and its existing test still passes
- [x] 4.2 Treat `MERGE_COMPACTION_PROMPT` as **unproven code** — covered by 7 new tests exercising it through `_compact_context` rather than by calling the formatter: merge routing, prefix exclusion, mismatch fallback, retry clearing, file carry-forward, mode logging, and the no-new-messages short circuit. Still unproven against a *real* model; that is task 6.4
- [x] 4.3 Confirm the file-operation tracking requirement still holds across a merge — `test_file_lists_carry_forward_across_a_held_state_merge`. The held summary is stored **with** its file blocks attached, so `_format_file_lists` can read them back; the merge prompt strips them, exactly as the marker path did. First draft of this test failed for its own reason — a trailing tool call sits in the retained tail and is never summarised, so it never reaches the file lists

## 5. Observability

- [x] 5.1 Log merge-versus-full at `WARNING` — the completion line now carries the mode and both counts: `Context compaction complete (merge): ... (2 of 11 messages sent to the model)`. The two counts are the saving, stated rather than inferred
- [x] 5.2 Write a test that both lines survive a `WARNING`-configured runner — `test_merge_and_full_paths_are_distinguishable_at_warning`

## 6. Verify

- [x] 6.1 Full task-runner suite green — 321 pass (301 baseline + 20 new)
- [x] 6.2 Drive two compactions in one run and confirm the second is a merge, sending only the new messages — `test_second_compaction_merges_when_the_held_summary_matches` and `test_merge_sends_only_the_messages_beyond_the_covered_prefix`, both driving `_compact_context` twice with the SDK's rebuild simulated (original messages returned, plus new turns)
- [x] 6.3 Confirm a mismatch genuinely falls back rather than merging anyway — `test_the_digest_is_what_rejects_a_mismatch` is a mutation guard: with `_digest_messages` neutralised across **both** compactions, the tampered history *is* merged onto. That the outcome flips is the evidence the check does the work rather than the merge path simply never engaging
- [ ] 6.4 Deploy and confirm via Loki: `{app="task-runner"} |= "Context compaction"` should show one full summarisation followed by merges, where the baseline showed four full summarisations in 104 seconds each re-covering the same 49 messages

## 7. Ship

- [ ] 7.1 Commit, push, open a PR
- [ ] 7.2 CI green
- [ ] 7.3 Deploy and run 6.4 against the deployment
- [ ] 7.4 Merge, delete branch
- [ ] 7.5 Archive the change so its deltas reach `openspec/specs/` — `fix-context-compaction` was merged without archiving and left the main specs stale for a day

## 8. Deliberately not addressed

- [x] 8.1 Making compaction persist across turns. The SDK does not support it: `call_model_input_filter` is per-call by construction, sessions are read once before the turn loop, and maintainers have declined to add a provider-agnostic equivalent (issue #2671 remains open)
- [x] 8.2 The overflow-retry architecture (strix, koder, Datus) — compact between runs and restart `Runner` with the compacted history. The only approach that genuinely persists, and errand is closer to it than expected since it already retries around `Runner.run_streamed()`. Its own change
- [x] 8.3 Evicting reconstructible tool outputs before summarising — the Manus tiering, and `agents.extensions.ToolOutputTrimmer` (undocumented, provider-agnostic). Probably higher value than anything here, since errand's context is dominated by large file reads. Its own change
- [x] 8.4 Changing `KEEP_RECENT_TOKENS`. Settled: 20,000 is the convergent constant across Cline and Codex
- [x] 8.5 A forced full re-summarisation every N merges, to bound drift. No published guidance found on where that threshold should sit; add a generation counter if quality degradation is observed
