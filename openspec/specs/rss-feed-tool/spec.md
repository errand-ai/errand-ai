## ADDED Requirements

### Requirement: read_rss_feed MCP tool
The MCP server SHALL expose a `read_rss_feed` tool that accepts `url` (str, required), `max_items` (int, optional, default 20), and `since` (str, optional, ISO 8601 datetime). The tool SHALL fetch the feed URL using `httpx`, parse it using `feedparser`, and return a JSON string containing a `feed` object (with `title`, `link`, `description`) and an `items` array. Each item SHALL include `title`, `link`, `published` (ISO 8601 or empty string if absent), and `summary` (first 500 characters of the entry description/summary, or empty string). Items SHALL be sorted by published date descending (newest first). If `since` is provided, only items published after that datetime SHALL be included. If `max_items` is provided, the result SHALL be limited to that many items.

#### Scenario: Fetch an RSS feed
- **WHEN** `read_rss_feed` is called with a valid RSS 2.0 feed URL
- **THEN** the tool returns a JSON string with `feed` metadata and up to 20 `items` sorted newest first

#### Scenario: Fetch an Atom feed
- **WHEN** `read_rss_feed` is called with a valid Atom feed URL
- **THEN** the tool returns the same JSON structure as for RSS feeds (feedparser normalises the format)

#### Scenario: Limit items with max_items
- **WHEN** `read_rss_feed` is called with `max_items=5` on a feed with 50 items
- **THEN** only the 5 most recent items are returned

#### Scenario: Filter items with since parameter
- **WHEN** `read_rss_feed` is called with `since="2026-04-20T00:00:00Z"` on a feed with items from April 15-25
- **THEN** only items published after April 20 are returned

#### Scenario: Feed with missing item dates
- **WHEN** `read_rss_feed` is called on a feed where some items have no published date
- **THEN** items without dates have `published` set to empty string and are sorted after dated items

#### Scenario: Feed fetch failure
- **WHEN** `read_rss_feed` is called with a URL that is unreachable or returns non-2xx
- **THEN** the tool returns a JSON string with an `error` key describing the failure

#### Scenario: Invalid feed content
- **WHEN** `read_rss_feed` is called with a URL that returns HTML instead of RSS/Atom XML
- **THEN** the tool returns a JSON string with an `error` key indicating the URL does not contain a valid feed

#### Scenario: Feed fetch timeout
- **WHEN** `read_rss_feed` is called and the HTTP request exceeds a 30-second timeout
- **THEN** the tool returns a JSON string with an `error` key indicating a timeout

### Requirement: read_rss_feed has no platform dependency
The `read_rss_feed` tool SHALL NOT depend on any platform being configured. It SHALL always be available as an MCP tool regardless of platform credential status. It follows the same pattern as `read_url`.

#### Scenario: read_rss_feed available without platforms
- **WHEN** a client sends a `tools/list` request to `/mcp` and no platforms have credentials configured
- **THEN** the `read_rss_feed` tool is included in the tool list

### Requirement: feedparser dependency
The project SHALL add `feedparser` to `errand/requirements.txt`. The version SHALL be pinned (e.g. `feedparser>=6.0,<7`).

#### Scenario: feedparser installed in venv
- **WHEN** `errand/.venv/bin/pip list` is run
- **THEN** `feedparser` appears in the installed packages list
