Requested official URL: https://hermes-agent.nousresearch.com/docs/developer-guide/acp-internals
Accessed UTC: 2026-10-03T14:55:12.479774+00:00
Title: ACP Internals | Hermes Agent
Retrieval: documentation extraction; excerpt may be abbreviated. Not a runtime test. Trailing whitespace normalized.

* [](https://hermes-agent.nousresearch.com/docs/)
* Developer Guide
* Internals
* ACP Internals
On this page

# ACP Internals
The ACP adapter wraps Hermes' synchronous `AIAgent` in an async JSON-RPC stdio server.
Key implementation files:
* `acp_adapter/entry.py`
* `acp_adapter/server.py`
* `acp_adapter/session.py`
* `acp_adapter/events.py`
* `acp_adapter/permissions.py`
* `acp_adapter/tools.py`
* `acp_adapter/auth.py`

...

## Major components ​
### `HermesACPAgent` ​
`acp_adapter/server.py` implements the ACP agent protocol.
Responsibilities:
* initialize / authenticate
* new/load/resume/fork/list/cancel session methods
* prompt execution
* session model switching
* wiring sync AIAgent callbacks into ACP async notifications

...

### Tool rendering helpers ​
`acp_adapter/tools.py` maps Hermes tools to ACP tool kinds and builds editor-facing content.
Examples:

...

## Related files ​
[Edit this page](https://github.com/NousResearch/hermes-agent/edit/main/website/docs/developer-guide/acp-internals.md)
[Previous Browser CDP Supervisor](https://hermes-agent.nousresearch.com/docs/developer-guide/browser-supervisor) [Next Cron Internals](https://hermes-agent.nousresearch.com/docs/developer-guide/cron-internals)
