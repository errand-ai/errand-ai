## 1. Branch and version

- [x] 1.1 Create branch `pin-constraints-across-compaction` from an up-to-date `main`
- [x] 1.2 Bump `VERSION` (minor — behaviour change to what survives compaction) — `0.143.0` → `0.144.0`

## 2. Sequence against the other compaction change

Both this and `reduce-compaction-recomputation` edit the split in `_compact_context`. Settle the order before writing code, not after.

- [x] 2.1 Decide which of the two lands first and record it in both changes. They are compatible in principle — one constrains where the split may fall (never between a `function_call` and its `function_call_output`), the other what is excluded from summarisation (`messages[0]`) — but developed blind to each other they will conflict — **decided: `reduce-compaction-recomputation` lands first.** Its split-point bug can orphan a tool call from its result and fail a live task; this change costs safety margin but is not actively breaking runs. Recorded in that change's `tasks.md` §1.3
- [x] 2.2 If this one lands second, rebase onto the other before starting — **done**: `reduce-compaction-recomputation` merged as `210bf77`, and this branch is cut from that `main`, so no rebase was needed. **This one lands second**, so rebase onto `main` after `reduce-compaction-recomputation` merges. Expect to touch the same lines: that change snaps `split_idx` forward to a tool-pair boundary, this one reserves `messages[0]` from the summarised portion. Both operate on `split_idx`, so reconcile rather than reapply

## 3. Preserve the initial task prompt

The structural fix, and the whole reason this change exists.

- [x] 3.1 Write failing tests first — `test_first_message_is_present_and_byte_identical_after_compaction`, `test_first_message_is_not_sent_for_summarisation`, `test_the_summary_follows_the_preserved_prompt`
- [x] 3.2 Write a failing test that a large first message is preserved in full rather than truncated — `test_a_large_first_message_is_preserved_in_full` (~56k-char prompt, asserted byte-identical)
- [x] 3.3 Write a test asserting trimming and compaction agree — `test_trimming_and_compaction_agree_about_the_first_message`
- [x] 3.4 Exclude `messages[0]` from the summarised portion and carry it through ahead of the summary — `to_summarize = messages[1:split_idx]`, result assembled as `preserved + [summary] + to_keep`
- [x] 3.5 Confirm this composes with the clamp — the lower bound moves from 1 to 2 (`max(2, min(split_idx, len-1))`), so one message is preserved, at least one summarised and at least one kept. `len(messages) > 2` is guaranteed at entry, so the bounds cannot cross. `test_the_clamp_reserves_room_for_the_preserved_prompt` pins it
- [x] 3.6 Confirm no double-counting — `test_first_message_is_not_sent_for_summarisation` asserts the prompt text is absent from the serialised conversation. Preserved means excluded, not duplicated; otherwise it would be paraphrased and pinned at once

## 4. Carry later constraints through the summary

Covers what the structural fix cannot: constraints arriving mid-task from a skill, a tool result, or a follow-up.

- [x] 4.1 Add a constraints section to both prompts — `## Constraints`, instructing original wording over paraphrase and preferring a borderline item over omission (recall before precision)
- [x] 4.2 Write a test that both prompts contain the instruction — `test_both_compaction_prompts_ask_for_constraints`
- [x] 4.3 Confirm a summarised portion containing no constraints still produces a normal summary — `test_a_conversation_without_constraints_still_summarises_normally`
- [ ] 4.4 Check the added section against the token budget — it takes space from Progress and Key Decisions, which is a real trade rather than a free addition

## 5. Observability

- [x] 5.1 Log preservation and the size preserved at `WARNING`
- [x] 5.2 Write a test that the line survives a `WARNING`-configured runner — `test_preservation_is_logged_at_warning`

## 6. Verify

- [x] 6.1 Task-runner suite green — 332 pass (321 baseline + 11 new)
- [x] 6.2 Structural check — `test_first_message_is_present_and_byte_identical_after_compaction` asserts full dict equality, not just the text
- [ ] 6.3 Empirical check, which is not: run a task whose prompt carries an explicit prohibition, past the compaction threshold, and inspect the post-compaction context for the instruction. The GetBookable review shape works — it compacted four times and its prompt said "Do not open pull requests, push commits, or modify the repository"
- [ ] 6.4 Confirm via Loki that the preservation line appears, using the same `{app="task-runner"} |= "Context compaction"` query that confirmed `fix-context-compaction`

## 7. Ship

- [x] 7.1 Commit, push, open a PR — [#238](https://github.com/errand-ai/errand-ai/pull/238)
- [x] 7.2 CI green — all 13 checks pass, `mergeStateStatus: CLEAN`
- [ ] 7.3 Deploy and run 6.3 against the deployment
- [ ] 7.4 Merge, delete branch
- [ ] 7.5 Archive the change so its deltas reach `openspec/specs/` — `fix-context-compaction` was merged without archiving and left the main specs stale for a day

## 8. Deliberately not addressed

- [ ] 8.1 Skill content reaching the model as tool results, and therefore being compactable. A real gap, but fixing it changes how skills are delivered. Audit the system skills first (open question in design): if they are purely procedural this is low priority; if any carry load-bearing constraints it is not
- [ ] 8.2 Enforcing constraints. This change is about survival only — nothing checks what the model does afterwards
- [ ] 8.3 Adversarial hardening against the Compaction-Eviction Attack. Preserving the prompt verbatim removes the summariser's discretion over that text, which addresses the mechanism, but is not a robustness claim
- [ ] 8.4 A structured constraints field on the task, so pinning is unambiguous rather than best-effort prose parsing. Larger change; noted in design
