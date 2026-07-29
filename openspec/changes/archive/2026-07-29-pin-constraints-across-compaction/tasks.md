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
- [x] 4.4 Check the added section against the token budget — assessed, and the trade is smaller than the design feared.

  **Input cost: negligible.** The instruction is 44 words (~60 tokens) added to a prompt that already carries the whole summarised conversation.

  **Output cost: 6 sections now compete for `compaction_max_tokens` (4096) where 5 did before** — nominally ~17% more claimants. But the two changes compose in our favour: with `messages[0]` preserved verbatim, prompt-borne constraints no longer need to appear in the summary at all, so on a typical task the section is empty or a line or two. It only carries weight for constraints arriving mid-task, which is exactly the case it exists for.

  **Residual risk, accepted:** a task accumulating many verbatim mid-task constraints could crowd out Progress. Mitigation already exists — `compaction_max_tokens` became an operator setting in `fix-context-compaction` (raised 2048 → 4096), so it can be lifted without a code change. Not worth pre-emptively capping the section, since truncating a constraint mid-sentence is the failure this change exists to prevent (same reasoning as the rejected cap on the preserved prompt in `design.md`).

## 5. Observability

- [x] 5.1 Log preservation and the size preserved at `WARNING`
- [x] 5.2 Write a test that the line survives a `WARNING`-configured runner — `test_preservation_is_logged_at_warning`

## 6. Verify

- [x] 6.1 Task-runner suite green — 332 pass (321 baseline + 11 new)
- [x] 6.2 Structural check — `test_first_message_is_present_and_byte_identical_after_compaction` asserts full dict equality, not just the text
- [ ] 6.3 **BLOCKED — attempted four times, never completed.** Empirical check: run a task whose prompt carries an explicit prohibition past the compaction threshold and inspect the post-compaction context for the instruction. Method used: an arbitrary magic phrase (`CRIMSON-PANGOLIN-47`) rather than guessable constraint text, because a model can reconstruct a plausible-sounding prohibition without having read it — only an arbitrary token distinguishes survival from confabulation.

  Why each attempt failed:

  1. `21a4bdc4` — prompt said "read EVERY file, do not stop early": an unbounded workload that ran 66 minutes. Then the ArgoCD rollover of *this PR* triggered the new server pod's startup orphan cleanup, which deleted the in-flight Job (`retry_count: 3`). **Deploying the change killed the task verifying the change.**
  2. `db9b2dd7` — same unbounded instruction. 32 compactions, context still growing 152k → 552k tokens; killed at 82 minutes.
  3. `1f11492e` / `08ca7845` — bounded to 50 files, but asking for per-file commentary produced a text-only turn, which the SDK treats as the final answer and ends the agent. Reworded to forbid prose; then the alphabetically-first 50 files proved too small — **50 files read, 0 compactions**.
  4. `819d7342` — 40 *largest* files on `claude-sonnet-4-5` for a reliable answerer. Failed with `litellm.ContextWindowExceededError` / `BedrockException: Input is too long` **before compaction fired**.

  Three of the four failures were task-design errors on my part, not defects. The fourth is a genuine finding and the more valuable outcome — see the token-estimate risk in `design.md`.

  This is **not evidence against the change**: no attempt reached a compaction *and* a final answer together. The structural half is verified by 6.2 (unit tests, byte-identical) and 6.4 (~64 preservation lines in production). What remains untested is only whether a model will quote back text it demonstrably received.
- [x] 6.4 Confirm via Loki that the preservation line appears — **confirmed on `0.144.0-pr238.1081`**: `Context compaction preserved the initial prompt verbatim (~N tokens, excluded from summarisation)` fired on **every** compaction observed across four runs (~64 total), at 564–735 tokens depending on prompt size. Also confirmed the merge path from `reduce-compaction-recomputation` still works alongside preservation, and that the no-new-messages short circuit fires

## 7. Ship

- [x] 7.1 Commit, push, open a PR — [#238](https://github.com/errand-ai/errand-ai/pull/238)
- [x] 7.2 CI green — all 13 checks pass, `mergeStateStatus: CLEAN`
- [x] 7.3 Deploy and run 6.3 against the deployment — deployed as `0.144.0-pr238.1081` and exercised heavily (~64 compactions across four tasks). 6.4 confirmed against it; 6.3 attempted four times and blocked (see 6.3)
- [ ] 7.4 Merge, delete branch
- [x] 7.5 Archive the change so its deltas reach `openspec/specs/` — archived **on the branch, before merge**, so PR #238 carries implementation and spec sync together. `task-runner-context-compaction` goes 10 → 13 requirements. `fix-context-compaction` was merged without archiving and left the main specs stale for a day, which forced a branch reconstruction

## 8. Deliberately not addressed

- [x] 8.1 Skill content reaching the model as tool results, and therefore being compactable — confirmed out of scope. **The audit was NOT performed**, so the priority question stays open: if any system skill carries a load-bearing constraint rather than pure procedure, this matters more than "low priority". Carried forward as a follow-up rather than silently closed
- [x] 8.2 Enforcing constraints — confirmed out of scope. Note the live evidence from task `21a4bdc4`: with the constraints fully visible in context, the agent still wrote a file into the cloned repo against "do NOT modify the repository in any way", then self-corrected mid-answer. Survival is necessary and demonstrably not sufficient
- [x] 8.3 Adversarial hardening against the Compaction-Eviction Attack — confirmed out of scope. Preserving `messages[0]` removes the summariser's discretion over that text, which addresses the mechanism structurally, but this is not a robustness claim
- [x] 8.4 A structured constraints field on the task — confirmed out of scope. Would make pinning unambiguous rather than best-effort; larger change, noted in `design.md`
