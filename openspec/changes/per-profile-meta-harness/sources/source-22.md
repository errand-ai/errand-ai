Requested official URL: https://hermes-agent.nousresearch.com/docs/developer-guide/programmatic-integration
Accessed UTC: 2026-10-03T14:55:12.500805+00:00
Title: Programmatic Integration | Hermes Agent
Retrieval: documentation extraction; excerpt may be abbreviated. Not a runtime test. Trailing whitespace normalized.

* [](https://hermes-agent.nousresearch.com/docs/)
* Developer Guide
* Architecture
* Programmatic Integration
On this page

# Programmatic Integration
Hermes ships three protocols for driving the agent from external programs — IDE plugins, custom UIs, CI pipelines, embedded sub-agents. Pick the one that matches your transport and consumer.

...

## ACP (Agent Client Protocol) ​
Capabilities exposed: session creation, prompt submission, streaming agent message chunks, tool-call events, permission requests, session fork, cancel, and authentication. Tool output is rendered into ACP `Diff` / `ToolCall` content blocks the IDE understands.
Full lifecycle, event bridge, and approval flow: [ACP Internals](https://hermes-agent.nousresearch.com/docs/developer-guide/acp-internals) .

...

## TUI Gateway JSON-RPC ​
### Server→client requests (questions the agent asks you) ​
A WebSocket client that never does is treated as a build that predates server→client requests: the gateway fails every such request for it immediately (the agent sees the same "no answer" an error response produces; an approval is withdrawn, not denied) instead of stalling for the full deadline.

...

## OpenAI-Compatible API Server ​
### Model catalog surfaces ​
The OpenAI-compatible API intentionally keeps `GET /v1/models` minimal: it is
the compatibility endpoint frontends expect, not the full Hermes provider/model
picker catalog.

...

## A note on `--mode rpc` ​
[Edit this page](https://github.com/NousResearch/hermes-agent/edit/main/website/docs/developer-guide/programmatic-integration.md)
