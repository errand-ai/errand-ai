## MODIFIED Requirements

### Requirement: Iterative compaction via summary merging
The task runner SHALL merge new context into an existing compaction summary on subsequent compactions rather than re-summarizing from scratch.

The previous summary SHALL be held in the task runner's own state, together with a record of exactly which messages it covered. It SHALL NOT be detected by searching the conversation for a summary marker: the compacted message list is not persisted by the agent framework, so no later compaction ever observes a prior summary in the history, and detection by marker cannot succeed.

The record SHALL identify the covered messages by their content, not by index or count. Indices shift as the framework rebuilds the message list between turns, and a count does not establish identity.

The task runner SHALL fall back to a full summarization whenever the record does not match the messages about to be summarized, or no record is held. An unnecessary full summarization costs time; a summary merged onto messages it does not describe misrepresents the conversation to the model without any error being raised.

The summary state SHALL be reset on the same boundary as the compaction backoff state, so a retried agent attempt does not inherit a summary from the attempt before it.

#### Scenario: Subsequent compaction with existing summary
- **WHEN** compaction is triggered and a held summary matches the messages being summarized
- **THEN** the task runner SHALL use a merge prompt that instructs the LLM to update the existing summary with new information
- **THEN** the merged summary SHALL preserve existing information, update progress, and add new decisions and context

#### Scenario: Progress tracking across compactions
- **WHEN** a merge compaction occurs and tasks have been completed since the previous summary
- **THEN** the merged summary SHALL move completed items from in-progress to done

#### Scenario: Only new messages are summarized on a merge
- **WHEN** a held summary covers a prefix of the messages being summarized
- **THEN** only the messages beyond that prefix SHALL be sent for summarization

#### Scenario: No new messages beyond the held summary
- **WHEN** the held summary covers exactly the messages about to be summarized, leaving nothing new
- **THEN** the task runner SHALL reuse the held summary without making a summarization call

#### Scenario: Content mismatch falls back to a full summarization
- **WHEN** the held record does not match the messages being summarized
- **THEN** the task runner SHALL perform a full summarization rather than merging

#### Scenario: No held summary falls back to a full summarization
- **WHEN** compaction runs with no summary held
- **THEN** the task runner SHALL perform a full summarization

#### Scenario: State does not leak across agent attempts
- **WHEN** an agent attempt is retried
- **THEN** the held summary SHALL be cleared, as the backoff state is

## ADDED Requirements

### Requirement: The compaction split never orphans a tool call from its result

The boundary between the summarized and retained portions of the conversation SHALL NOT fall between a `function_call` and its matching `function_call_output`.

Where the token-based boundary would separate them, it SHALL be moved forward — placing more of the conversation into the summarized portion — until it falls at a point with no tool call left open. Moving it forward errs toward reclaiming more context; moving it backward would retain a larger tail and could leave the conversation still over the limit after a compaction that reported success, which fails silently rather than merely cutting deeper.

An orphaned `function_call_output` at the head of the retained portion is rejected by the provider, and would occur precisely when the context is already under pressure.

#### Scenario: Boundary inside a tool call pair is moved

- **WHEN** the token-based boundary falls between a `function_call` and its `function_call_output`
- **THEN** the boundary is moved forward to a point where no tool call is left open

#### Scenario: Retained portion never begins with an orphaned result

- **WHEN** compaction completes
- **THEN** the retained portion contains no `function_call_output` whose `function_call` was summarized

#### Scenario: Safe boundary is left alone

- **WHEN** the token-based boundary already falls at a point with no tool call open
- **THEN** it is used unchanged

#### Scenario: Moving the boundary may retain less than the target

- **WHEN** moving the boundary forward past a large tool call pair reduces the retained portion below `KEEP_RECENT_TOKENS`
- **THEN** compaction proceeds, preferring a deeper cut to an invalid conversation

### Requirement: Merge and full compaction are distinguishable in logs

The task runner SHALL log whether a compaction merged into a held summary or performed a full summarization, at `WARNING` or above.

Production runs the task runner above `INFO`. Without this, whether chaining engaged is answerable only by inferring from call timings — the same position that left the original compaction defect invisible for weeks.

#### Scenario: A merge is identifiable

- **WHEN** a compaction merges into a held summary at `WARNING`
- **THEN** the log line identifies it as a merge

#### Scenario: A full summarization is identifiable

- **WHEN** a compaction summarizes from scratch at `WARNING`
- **THEN** the log line identifies it as a full summarization
