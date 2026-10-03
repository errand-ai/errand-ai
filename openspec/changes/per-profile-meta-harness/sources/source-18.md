Requested official URL: https://hermes-agent.nousresearch.com/docs/user-guide/features/api-server
Accessed UTC: 2026-10-03T14:55:12.440797+00:00
Title: API Server | Hermes Agent
Retrieval: documentation extraction; excerpt may be abbreviated. Not a runtime test. Trailing whitespace normalized.

* [](https://hermes-agent.nousresearch.com/docs/)
* Features
* Management
* API Server
On this page

# API Server
The API server exposes hermes-agent as an OpenAI-compatible HTTP endpoint. Any frontend that speaks the OpenAI format — Open WebUI, LobeChat, LibreChat, NextChat, ChatBox, and hundreds more — can connect to hermes-agent and use it as a backend.
Your agent handles requests with its full toolset (terminal, file operations, web search, memory, skills) and returns the final response. When streaming, tool progress indicators appear inline so frontends can show what the agent is doing.
One backend covers models + tools
Hermes itself needs a configured provider and tool backends for the API server to be useful. A [Nous Portal](https://hermes-agent.nousresearch.com/docs/user-guide/features/tool-gateway) subscription handles both — 300+ models plus web/image/TTS/browser via the Tool Gateway. Run `hermes setup --portal` once before starting the API server and frontends like Open WebUI or LobeChat get a fully tool-equipped backend.

...

## Endpoints ​
### POST /v1/responses ​
#### Multi-turn with previous_response_id ​
Chain responses to maintain full context (including tool calls) across turns:
```
{ "input" : "Now show me the README" , "previous_response_id" : "resp_abc123" }
```
The server reconstructs the full conversation from the stored response chain — all previous tool calls and results are preserved. Chained requests also share the same session, so multi-turn conversations appear as a single entry in the dashboard and session history.

...

### GET /v1/models ​
Lists the agent as an available model. The advertised model name defaults to the [profile](https://hermes-agent.nousresearch.com/docs/user-guide/profiles) name (or `hermes-agent` for the default profile). Required by most frontends for model discovery.

...

### GET /api/model/options ​
That payload is the same substrate the dashboard Models page and the TUI `model.options` RPC use. It returns authenticated providers, curated model
lists, per-model pricing, and model capability hints.

...

## Proxy Mode ​
See [Matrix Proxy Mode](https://hermes-agent.nousresearch.com/docs/user-guide/messaging/matrix) for the full setup guide.
[Edit this page](https://github.com/NousResearch/hermes-agent/edit/main/website/docs/user-guide/features/api-server.md)
