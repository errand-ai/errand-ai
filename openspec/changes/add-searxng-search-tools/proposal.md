## Why

The task-runner agent needs web search capabilities to research topics, gather information, and verify facts while executing tasks. A self-hosted SearXNG instance is deployed at `https://search.errand.cloud` and the errand MCP server needs tools to expose search and URL reading to the agent.

## What Changes

- Extend `PlatformCapability` enum with a `SEARCH` capability value
- Add a `search()` method to the `Platform` base class (raises `NotImplementedError` by default)
- Create a `SearXNGPlatform` implementing search via the SearXNG JSON API, with optional HTTP Basic Auth
- Add a `searxng_url` setting to the settings registry with default `https://search.errand.cloud`
- Register `SearXNGPlatform` in application startup
- Add `web_search` MCP tool that delegates to `SearXNGPlatform.search()`
- Add `read_url` MCP tool as a standalone utility (fetches any URL, converts HTML to markdown)
- Add `httpx` and `html2text` as Python dependencies

## Capabilities

### New Capabilities
- `searxng-search`: SearXNG platform integration with web search and URL reading MCP tools
- `read-url-tool`: Standalone MCP tool for fetching and converting web pages to markdown

### Modified Capabilities
- `platform-abstraction`: Add `SEARCH` to `PlatformCapability` enum and `search()` method to `Platform` base class
- `mcp-server-endpoint`: Add `web_search` and `read_url` tools to the MCP server tool list

## Impact

- **Backend**: New `errand/platforms/searxng.py` module; modifications to `errand/platforms/base.py`, `errand/mcp_server.py`, `errand/main.py`, `errand/settings_registry.py`
- **Dependencies**: `httpx` and `html2text` added to `errand/requirements.txt`
- **Frontend**: No changes — `SearXNGPlatform` renders automatically via existing `PlatformSettings` UI
- **Deployment**: SearXNG instance URL configurable via integrations page; authentication optional (reverse proxy basic auth)
