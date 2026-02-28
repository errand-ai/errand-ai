## Purpose

Standalone MCP tool for fetching web pages and converting HTML content to markdown, enabling the task-runner agent to read and process web page content.

## ADDED Requirements

### Requirement: read_url MCP tool

The MCP server SHALL expose a `read_url` tool that accepts `url` (str, required) and `max_length` (int, optional, default 50000). The tool SHALL fetch the URL using `httpx`, convert the HTML response body to markdown using `html2text`, truncate to `max_length` characters, and return a JSON string with keys: `url`, `title` (from the HTML `<title>` tag, or empty string if absent), and `content` (the markdown text).

#### Scenario: Read a web page

- **WHEN** `read_url` is called with a valid URL that returns HTML
- **THEN** the tool returns a JSON string containing the URL, page title, and markdown-converted content

#### Scenario: Read a page with no title

- **WHEN** `read_url` is called with a URL whose HTML has no `<title>` tag
- **THEN** the returned JSON has `title` set to an empty string

#### Scenario: Content truncation

- **WHEN** `read_url` is called and the converted markdown exceeds `max_length` characters
- **THEN** the content is truncated to `max_length` characters

#### Scenario: Custom max_length

- **WHEN** `read_url` is called with `max_length=10000`
- **THEN** the content is truncated to 10000 characters if it exceeds that length

#### Scenario: URL fetch failure

- **WHEN** `read_url` is called with a URL that returns a non-2xx status code or is unreachable
- **THEN** the tool returns a JSON string with an `error` key describing the failure

#### Scenario: Timeout handling

- **WHEN** `read_url` is called and the HTTP request exceeds a 30-second timeout
- **THEN** the tool returns a JSON string with an `error` key indicating a timeout

### Requirement: read_url has no platform dependency

The `read_url` tool SHALL NOT depend on any platform being configured. It SHALL always be available as an MCP tool regardless of platform credential status.

#### Scenario: read_url available without platforms

- **WHEN** a client sends a `tools/list` request to `/mcp` and no platforms have credentials configured
- **THEN** the `read_url` tool is included in the tool list
