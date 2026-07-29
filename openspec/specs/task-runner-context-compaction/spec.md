## Purpose

LLM-based context-window compaction for the task-runner: iterative summarization, file-operation tracking across compactions, and a configurable compaction model.

## Requirements
### Requirement: Context compaction via LLM summarization
The task runner SHALL replace dropped messages with an LLM-generated structured summary when the conversation exceeds the context token budget.

#### Scenario: First compaction triggered
- **WHEN** estimated tokens exceed `MAX_CONTEXT_TOKENS` minus a reserve buffer
- **THEN** the task runner SHALL identify a split point that keeps approximately 20,000 tokens of recent messages
- **THEN** the task runner SHALL serialize older messages into a text representation
- **THEN** the task runner SHALL call the LLM with a summarization prompt to produce a structured checkpoint
- **THEN** the task runner SHALL replace the older messages with the summary as a single user-role message

#### Scenario: Summary structure
- **WHEN** a compaction summary is generated
- **THEN** the summary SHALL contain sections for: Goal, Progress (done/in-progress/blocked), Key Decisions, Next Steps, and Files (read/modified)

#### Scenario: Messages under budget
- **WHEN** estimated tokens are under `MAX_CONTEXT_TOKENS` minus the reserve buffer
- **THEN** the task runner SHALL NOT trigger compaction and SHALL pass messages through unchanged

### Requirement: Iterative compaction via summary merging
The task runner SHALL merge new context into an existing compaction summary on subsequent compactions rather than re-summarizing from scratch.

The previous summary SHALL be held in the task runner's own state, together with a record of exactly which messages it covered. The task runner SHALL NOT depend on detecting a prior summary by searching the conversation for a marker: the agent framework does not write the compacted message list back into the conversation, so a later compaction cannot rely on observing one. A marker check MAY be retained as a fallback for a summary that reaches the history by some other route, but it SHALL NOT be the primary mechanism.

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

### Requirement: File operation tracking across compactions
The task runner SHALL track files read and modified by the agent across compaction boundaries.

#### Scenario: File operations extracted from tool calls
- **WHEN** compaction processes messages containing `execute_command` tool calls
- **THEN** the task runner SHALL scan commands for file read operations (cat, head, tail, grep) and file write operations (redirects, sed -i, tee, cp, mv)
- **THEN** the task runner SHALL append `<read-files>` and `<modified-files>` XML blocks to the summary

#### Scenario: File lists carried forward across compactions
- **WHEN** a subsequent compaction merges into an existing summary that contains file lists
- **THEN** the merged summary SHALL include file operations from both the previous summary and the new messages

### Requirement: Compaction model configuration
The task runner SHALL support configuring a separate model for summarization. The model SHALL be resolved as an operator setting (`compaction_model`) rather than only at deploy time, following the standard resolution order: the `COMPACTION_MODEL` environment variable overrides the setting, which overrides the default.

The default SHALL be the task's configured model (`OPENAI_MODEL`).

`compaction_model` SHALL be registered in `MODEL_SETTING_KEYS` so that `model` and `model_id` are mirrored on write and read. Without that registration a model chosen in the settings UI resolves to an empty string at runtime, because the shared settings card writes `model_id` while the backend resolves `model`.

#### Scenario: Custom compaction model from setting
- **WHEN** the `compaction_model` setting is set and `COMPACTION_MODEL` is not in the environment
- **THEN** the task runner SHALL use the setting's model for summarization LLM calls

#### Scenario: Environment overrides the setting
- **WHEN** `COMPACTION_MODEL` is set in the environment and the `compaction_model` setting is also set
- **THEN** the task runner SHALL use the environment value

#### Scenario: Default compaction model
- **WHEN** neither `COMPACTION_MODEL` nor the `compaction_model` setting is set
- **THEN** the task runner SHALL use the task's configured model (`OPENAI_MODEL`) for summarization

#### Scenario: Model chosen in the UI resolves at runtime
- **WHEN** an admin selects a compaction model in the settings UI, which writes `{provider_id, model_id}`
- **THEN** the stored value SHALL carry a `model` key equal to `model_id`, and the runner SHALL receive a non-empty model name

### Requirement: Compaction request timeout and token budget are configurable

The summarization call SHALL use a timeout resolved from the `compaction_timeout` setting (overridable by `COMPACTION_TIMEOUT_SECONDS`) and a maximum output token budget resolved from the `compaction_max_tokens` setting (overridable by `COMPACTION_MAX_TOKENS`).

The default timeout SHALL be large enough for a local or free-tier model to generate the full token budget. A 30-second default is insufficient: generating 2048 tokens takes 25–50 seconds on a locally served mixture-of-experts model before any prompt processing.

The compaction timeout SHALL NOT inherit `LLM_REQUEST_TIMEOUT`, preserving the existing separation between the streaming agent loop and this single non-streaming call.

#### Scenario: Timeout resolved from setting
- **WHEN** the `compaction_timeout` setting is 180 and `COMPACTION_TIMEOUT_SECONDS` is unset
- **THEN** the summarization client SHALL be constructed with a 180-second timeout

#### Scenario: Token budget resolved from setting
- **WHEN** the `compaction_max_tokens` setting is 4096
- **THEN** the summarization request SHALL be made with `max_tokens` of 4096

#### Scenario: Invalid values fall back to the default
- **WHEN** `COMPACTION_TIMEOUT_SECONDS` is not a positive number
- **THEN** the task runner SHALL log a warning and use the default timeout

#### Scenario: Agent timeout is unaffected
- **WHEN** `LLM_REQUEST_TIMEOUT` is set to 30
- **THEN** the compaction timeout SHALL be unchanged by it

### Requirement: Failed compaction backs off instead of retrying every turn

Compaction runs from the pre-model input filter, which is invoked before every model request. After a failed compaction the task runner SHALL suppress further compaction attempts for a number of subsequent turns that grows with each consecutive failure, up to a cap, falling through to context trimming during the suppression window.

A successful compaction SHALL reset the failure count and the suppression window.

Entering and leaving the suppression window SHALL be logged at `WARNING`, so a task that stops compacting is visible rather than silent.

#### Scenario: Second consecutive failure widens the window
- **WHEN** compaction fails twice in a row
- **THEN** the suppression window after the second failure SHALL be longer than after the first

#### Scenario: Suppressed turns do not call the summarization LLM
- **WHEN** a turn falls inside the suppression window and the context is over the limit
- **THEN** the task runner SHALL trim without making a summarization LLM call

#### Scenario: Success resets the backoff
- **WHEN** a compaction succeeds after previous failures
- **THEN** the failure count SHALL reset, and the next over-limit turn SHALL attempt compaction

#### Scenario: A failing configuration costs bounded attempts
- **WHEN** compaction fails on every attempt for the duration of a task
- **THEN** the number of summarization calls SHALL be bounded by the backoff schedule rather than growing with the turn count

### Requirement: The compaction lifecycle is observable at the production log level

The task runner SHALL log compaction lifecycle events — triggered, complete, skipped, and every failure path — at `WARNING` or above. Context trimming SHALL also be logged at `WARNING`, because it discards conversation history irrecoverably.

Production runs the task runner above `INFO`. Logging failures at `WARNING` while logging the trigger and the success at `INFO` makes a broken mechanism observable and a working one silent, which is the wrong way round for confirming that a fix worked. It also makes "did compaction run at all?" unanswerable from logs, leaving operators to infer it from token arithmetic.

#### Scenario: A successful compaction is visible

- **WHEN** compaction completes successfully and the task runner is configured at `WARNING`
- **THEN** a log line reporting the completion is emitted

#### Scenario: The trigger is visible

- **WHEN** compaction is triggered and the task runner is configured at `WARNING`
- **THEN** a log line reporting the trigger, the estimated tokens and the limit is emitted

#### Scenario: Trimming is visible

- **WHEN** the context is trimmed and the task runner is configured at `WARNING`
- **THEN** a log line reporting the message and token counts before and after is emitted

#### Scenario: A skipped compaction is visible

- **WHEN** compaction is skipped because the model or API key is missing, at `WARNING`
- **THEN** a log line reporting the missing configuration is emitted

### Requirement: Empty summary responses are diagnosable

When the summarization call returns successfully but produces no usable summary text, the task runner SHALL log — at `WARNING`, since production runs the task runner above `INFO` — the response's finish reason, the length of the returned content, and whether a reasoning or thinking field was populated.

This distinguishes a model that declined to answer from one whose reasoning tokens consumed the entire output budget before any summary was emitted. The two have different remedies and are otherwise indistinguishable from the logs.

#### Scenario: Budget exhausted by reasoning
- **WHEN** the summarization response has empty content, a finish reason of `length`, and a populated reasoning field
- **THEN** the log line SHALL report all three, and the task runner SHALL fall back to trimming

#### Scenario: Empty content with no reasoning field
- **WHEN** the summarization response has empty content and no reasoning field
- **THEN** the log line SHALL report the finish reason and a content length of zero

#### Scenario: Diagnostics survive the production log level
- **WHEN** the task runner is configured at `WARNING`
- **THEN** the empty-summary diagnostic SHALL still be emitted

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

### Requirement: The initial task prompt survives compaction

Compaction SHALL NOT summarise the first message of the conversation. The first message SHALL be carried through verbatim, ahead of the generated summary, regardless of its size.

This matches the guarantee trimming already makes — `agent-context-management` requires that "the first message (initial user prompt) is always retained regardless of its size" — so the two context-management paths agree about whether the user's instructions are load-bearing.

The first message contains the task's own instructions, including any prohibitions and scope limits. Summarising it makes their survival depend on what the summariser chose to keep, on tasks that run unattended and whose tools post to Slack, send mail, write to cloud storage and push to git.

Preserving the message verbatim SHALL be preferred over extracting and re-injecting constraint text. Extraction requires deciding which text is a constraint, and a rule that misses one is worse than none, because it creates confidence that constraints are protected when they are not.

#### Scenario: First message is not summarised

- **WHEN** compaction runs on a conversation of many messages
- **THEN** the first message is not part of the summarised portion

#### Scenario: First message is present verbatim after compaction

- **WHEN** compaction completes
- **THEN** the resulting message list begins with the original first message, byte-identical to the input

#### Scenario: Summary follows the preserved prompt

- **WHEN** compaction completes
- **THEN** the generated summary appears after the preserved first message, not in place of it

#### Scenario: Large first message is still preserved

- **WHEN** the first message is large enough that preserving it consumes a significant share of the budget
- **THEN** it is preserved in full and not truncated

#### Scenario: A compaction summary at the first position is not preserved
- **WHEN** the first message is itself a compaction summary rather than an initial prompt
- **THEN** it SHALL NOT be preserved verbatim, and SHALL remain eligible for merging

Preserving it would pin a summary permanently and stop it ever being updated, which is worse than not preserving. A summary in that position means the original prompt was already summarised away, so there is nothing left to protect.

#### Scenario: Consistency with trimming

- **WHEN** the same conversation is trimmed instead of compacted
- **THEN** the first message is preserved by both paths

### Requirement: Compaction summaries carry constraints forward

The summarisation prompt SHALL instruct the model to record constraints — prohibitions, approval requirements, and scope limits — and to carry them forward in their original wording rather than paraphrased.

Preserving the first message protects constraints that arrived with the task. It does not protect constraints that arrive later: a skill read mid-task, a policy in a tool result, or a follow-up instruction. Those are summarised, so the summary must be biased toward retaining them.

#### Scenario: Constraint stated mid-task is carried forward

- **WHEN** a constraint appears in the conversation after the first message and that portion is summarised
- **THEN** the summarisation prompt directs the model to record it among the constraints

#### Scenario: Constraints are not paraphrased

- **WHEN** the summary records a constraint
- **THEN** the prompt directs that its original wording be retained rather than reworded

#### Scenario: No constraints present

- **WHEN** the summarised portion contains no constraints
- **THEN** the summary is produced normally with that section empty

### Requirement: Prompt preservation is observable

When compaction preserves the first message, the task runner SHALL log that it did so, and the size preserved, at `WARNING` or above.

Production runs the task runner above `INFO`, so a lower level would make this invisible in the deployment where it matters. Recording it means a task that somehow lost its instructions is detectable after the fact rather than inferred from behaviour.

#### Scenario: Preservation is logged at the production level

- **WHEN** compaction preserves the first message and the runner is configured at `WARNING`
- **THEN** a log line reporting the preservation and its size is emitted
