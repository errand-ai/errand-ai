## Context

The task-runner agent currently has no web search capability. A SearXNG instance is deployed at `https://search.errand.cloud` (unauthenticated for now). The errand MCP server already exposes task management and Twitter posting tools. The platform abstraction supports social platforms with post/delete/get operations but has no search concept.

The reference `mcp-searxng` server (github.com/ihor-sokoliuk/mcp-searxng) exposes two tools — `searxng_web_search` and `web_url_read` — which we use as functional inspiration but integrate directly into errand's existing architecture.

## Goals / Non-Goals

**Goals:**
- Extend the platform abstraction to support search as a first-class capability
- Add SearXNG as a platform with configurable URL and optional HTTP Basic Auth credentials
- Expose `web_search` and `read_url` MCP tools for the task-runner agent
- Return structured JSON from both tools so the LLM agent can process results programmatically

**Non-Goals:**
- SearXNG deployment or authentication infrastructure changes (handled separately)
- Image search, news-specific search, or other specialized search categories
- Caching or rate limiting of search requests
- Frontend changes beyond what the existing PlatformSettings UI provides automatically

## Decisions

### Decision 1: SearXNG as a Platform (not a standalone setting)

SearXNG is registered as a `Platform` with `SEARCH` capability. The URL is stored in the platform's `credential_schema` alongside optional basic auth credentials.

**Rationale**: The platform abstraction already handles credential storage, verification, and UI rendering. SearXNG will need authentication in the future, which maps directly to the credential model. This avoids creating a parallel "services" system.

**Alternative considered**: Store `searxng_url` in the settings registry as a simple setting. Rejected because it would bypass the credential system and require a custom UI section on the integrations page.

### Decision 2: `read_url` as a standalone MCP tool

The `read_url` tool is not tied to the SearXNG platform. It fetches any URL and converts HTML to markdown using `httpx` + `html2text`. It has no platform dependency and is always available.

**Rationale**: URL reading doesn't use SearXNG — it's a general utility. Tying it to the SearXNG platform would mean agents can't read URLs if SearXNG isn't configured.

### Decision 3: `search()` method on Platform base class

Add `async def search(self, query: str, **kwargs) -> dict` to the `Platform` base class with a default `NotImplementedError`. Only platforms with `SEARCH` capability override it.

**Rationale**: Follows the existing pattern where `post()`, `delete_post()`, and `get_post()` are optional methods that raise `NotImplementedError` by default. The capability enum tells callers what's available.

### Decision 4: SearXNG credential schema

```python
credential_schema = [
    {"key": "url", "label": "Instance URL", "type": "text", "required": True},
    {"key": "username", "label": "Username", "type": "text", "required": False},
    {"key": "password", "label": "Password", "type": "password", "required": False},
]
```

The URL field is required. Username/password are optional — when empty, requests are sent without auth. This supports the current unauthenticated deployment and future basic-auth-protected setups.

**Alternative considered**: Separate the URL into a setting and only use credentials for auth. Rejected because the platform credential system already supports mixed field types and keeping everything together simplifies the data flow.

### Decision 5: Structured JSON response format

`web_search` returns a JSON string with:
```json
{
  "query": "search terms",
  "results": [
    {"title": "...", "url": "...", "content": "...", "engines": [...], "score": 1.5}
  ],
  "suggestions": ["..."],
  "number_of_results": 42
}
```

`read_url` returns a JSON string with:
```json
{
  "url": "...",
  "title": "...",
  "content": "markdown content..."
}
```

**Rationale**: The consumer is an LLM agent that needs to programmatically decide which results to follow up on. JSON gives structure; the agent can parse and reason over results.

### Decision 6: Default URL via credential schema, not settings registry

The default SearXNG URL (`https://search.errand.cloud`) is used when no credentials are configured. The `web_search` tool checks for platform credentials first; if none exist, it falls back to the default URL without authentication.

**Rationale**: This means SearXNG works out of the box without requiring the user to configure anything on the integrations page. Users only need to visit integrations if they want to point to a different instance or add auth.

### Decision 7: Use `html2text` for HTML-to-markdown conversion

Add `html2text` as a new dependency for the `read_url` tool.

**Rationale**: `html2text` is a well-maintained, lightweight library specifically designed for HTML-to-markdown conversion. It handles common HTML patterns (tables, links, images, lists) and produces clean output. `httpx` (already a dependency) handles the HTTP fetching.

## Risks / Trade-offs

- **[SearXNG availability]** If the SearXNG instance is down, `web_search` will fail. → The tool returns a clear error message. No retry logic; the agent can decide whether to retry.
- **[Large HTML pages]** `read_url` could return very large content for complex pages. → Truncate content to a configurable max length (default 50,000 chars) to avoid overwhelming the agent context window.
- **[Credential-less default]** The default URL works without credentials, which means anyone with MCP access can search. → MCP already requires API key auth, so this is acceptable.
- **[html2text dependency]** New dependency added. → Well-maintained (10+ years), pure Python, no transitive dependencies of concern.
