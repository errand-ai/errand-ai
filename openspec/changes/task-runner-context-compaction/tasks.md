## 1. Summarization Prompts

- [ ] 1.1 Add `SUMMARIZATION_SYSTEM_PROMPT` constant — instructs the LLM to produce a structured summary only, not continue the conversation
- [ ] 1.2 Add `FIRST_COMPACTION_PROMPT` constant — template for initial compaction requesting Goal, Progress, Key Decisions, Next Steps, Critical Context sections
- [ ] 1.3 Add `MERGE_COMPACTION_PROMPT` constant — template for subsequent compactions that merges new information into an existing summary while preserving prior context

## 2. Helper Functions

- [ ] 2.1 Implement `_serialize_messages_for_summary(messages)` — converts message list to text representation with role labels and tool results truncated to ~2k chars, wrapped in `<conversation>` tags
- [ ] 2.2 Implement `_extract_file_operations(messages)` — scans `execute_command` tool calls for file read (cat, head, tail, grep) and write (>, >>, sed -i, tee, cp, mv) patterns, returns `(read_files, modified_files)` sets
- [ ] 2.3 Implement `_format_file_lists(read_files, modified_files, existing_summary)` — produces `<read-files>` and `<modified-files>` XML blocks, merging with any file lists from a prior summary
- [ ] 2.4 Implement `_is_compaction_summary(message)` — checks if a message is a compaction summary (by prefix marker)

## 3. Core Compaction

- [ ] 3.1 Implement `_compact_context(messages)` — main function: estimates tokens, finds split point (~20k recent tokens), calls summarization LLM, returns compacted message list with summary as first message
- [ ] 3.2 Add `COMPACTION_MODEL` env var support — reads from environment, defaults to `OPENAI_MODEL`
- [ ] 3.3 Create synchronous OpenAI client for summarization calls (separate from the async client used by the Agents SDK)
- [ ] 3.4 Handle subsequent compactions — detect existing summary in first message, use merge prompt instead of initial prompt, carry forward file lists

## 4. Integration

- [ ] 4.1 Replace `_trim_context_window` call in `filter_model_input` with `_compact_context`
- [ ] 4.2 Add `COMPACTION_SUMMARY_PREFIX` constant used to identify compaction summaries
- [ ] 4.3 Add logging for compaction events — tokens before, tokens after, number of messages summarized

## 5. Tests

- [ ] 5.1 Test compaction triggers when tokens exceed budget and produces structured summary
- [ ] 5.2 Test compaction does not trigger when tokens are under budget
- [ ] 5.3 Test subsequent compaction uses merge prompt and preserves prior summary content
- [ ] 5.4 Test file operation extraction from execute_command tool calls
- [ ] 5.5 Test file lists are carried forward across compactions
- [ ] 5.6 Test message serialization truncates tool results to ~2k chars
- [ ] 5.7 Test `COMPACTION_MODEL` env var is used when set, falls back to `OPENAI_MODEL`
- [ ] 5.8 Test compaction with 2 or fewer messages returns unchanged
