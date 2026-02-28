## 1. Platform Abstraction Extensions

- [x] 1.1 Add `SEARCH = "search"` to `PlatformCapability` enum in `errand/platforms/base.py`
- [x] 1.2 Add `search(self, query: str, **kwargs) -> dict` method to `Platform` base class (raises `NotImplementedError`)

## 2. SearXNG Platform

- [x] 2.1 Create `errand/platforms/searxng.py` with `SearXNGPlatform` class implementing `info()`, `verify_credentials()`, and `search()`
- [x] 2.2 Register `SearXNGPlatform` in app startup in `errand/main.py`

## 3. MCP Tools

- [x] 3.1 Add `web_search` MCP tool to `errand/mcp_server.py` — loads SearXNG credentials, falls back to default URL, delegates to `SearXNGPlatform.search()`, returns JSON string
- [x] 3.2 Add `read_url` MCP tool to `errand/mcp_server.py` — fetches URL with `httpx`, extracts title, converts HTML to markdown with `html2text`, returns JSON string with truncation

## 4. Dependencies

- [x] 4.1 Add `html2text` to `errand/requirements.txt`

## 5. Tests

- [x] 5.1 Add unit tests for `SearXNGPlatform` (info, verify_credentials, search) in `errand/tests/test_searxng.py`
- [x] 5.2 Add unit tests for `web_search` and `read_url` MCP tools in `errand/tests/test_mcp.py`
- [x] 5.3 Add test for `search()` method raising `NotImplementedError` on base `Platform` class
