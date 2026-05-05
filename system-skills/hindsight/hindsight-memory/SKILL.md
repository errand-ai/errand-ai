---
name: hindsight-memory
description: Persistent memory across tasks via the hindsight MCP server (recall, retain, reflect). Recall relevant context at task start; retain important learnings before completing the task.
---

You have access to a persistent memory store via the `hindsight` MCP server. The store survives across tasks — facts, decisions, patterns, and learnings you save are available to future runs.

## Available tools

- `recall` — search memories for context relevant to a query
- `retain` — store a fact, decision, pattern, or learning for future tasks
- `reflect` — synthesize reasoning across stored memories on a topic

## Recall at task start

Before beginning work, use `recall` to load relevant context. Choose your own query — the task title and description are a starting point, but the agent understands the task best and should formulate the query that will surface the most useful memories.

If `recall` returns nothing, proceed without prior context — this is normal for new topics.

## Retain at task end

Before completing the task, use `retain` to save anything that future tasks would benefit from knowing:

- Decisions you made and why
- Non-obvious patterns or conventions you discovered
- Workarounds for surprising behaviour
- Outcomes worth referencing later

Be concrete and specific. A retained memory should be useful in isolation — assume the next reader has no context from this run.

## Reflect for analysis

Use `reflect` when you need to reason across multiple memories on a topic (e.g. "what have we learned about deploying this service?"). Prefer `recall` for simple lookups.
