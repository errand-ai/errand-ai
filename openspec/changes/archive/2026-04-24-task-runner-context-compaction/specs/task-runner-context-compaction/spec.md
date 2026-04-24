## ADDED Requirements

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

#### Scenario: Subsequent compaction with existing summary
- **WHEN** compaction is triggered and the first message is already a compaction summary
- **THEN** the task runner SHALL use a merge prompt that instructs the LLM to update the existing summary with new information
- **THEN** the merged summary SHALL preserve existing information, update progress, and add new decisions and context

#### Scenario: Progress tracking across compactions
- **WHEN** a merge compaction occurs and tasks have been completed since the previous summary
- **THEN** the merged summary SHALL move completed items from in-progress to done

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
The task runner SHALL support configuring a separate model for summarization via the `COMPACTION_MODEL` environment variable.

#### Scenario: Custom compaction model
- **WHEN** `COMPACTION_MODEL` is set
- **THEN** the task runner SHALL use that model for summarization LLM calls

#### Scenario: Default compaction model
- **WHEN** `COMPACTION_MODEL` is not set
- **THEN** the task runner SHALL use the task's configured model (`OPENAI_MODEL`) for summarization
