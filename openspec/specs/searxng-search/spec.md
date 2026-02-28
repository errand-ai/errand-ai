## Purpose

SearXNG platform integration that provides web search capabilities via the platform abstraction, with configurable instance URL and optional HTTP Basic Auth.

## Requirements

### Requirement: SearXNG platform class

The system SHALL provide a `SearXNGPlatform` class in `errand/platforms/searxng.py` that extends the `Platform` base class. The class SHALL implement `info()`, `verify_credentials()`, and `search()`. The platform SHALL declare `PlatformCapability.SEARCH` in its capabilities.

#### Scenario: SearXNG platform info

- **WHEN** `SearXNGPlatform().info()` is called
- **THEN** the returned `PlatformInfo` has `id="searxng"`, `label="SearXNG Search"`, capabilities containing `PlatformCapability.SEARCH`, and a `credential_schema` with fields for `url`, `username`, and `password`

### Requirement: SearXNG credential schema

The `SearXNGPlatform` credential schema SHALL include: `url` (text, required) for the SearXNG instance URL, `username` (text, optional) for HTTP Basic Auth username, and `password` (password, optional) for HTTP Basic Auth password.

#### Scenario: Credential schema structure

- **WHEN** `SearXNGPlatform().info().credential_schema` is inspected
- **THEN** it contains three fields: `url` (required), `username` (not required), `password` (not required)

### Requirement: SearXNG credential verification

The `verify_credentials()` method SHALL send a GET request to `{url}/search?q=test&format=json` (with Basic Auth if username/password are provided). It SHALL return `True` if the response status is 200 and the response body contains a `results` key. It SHALL return `False` for any error or non-200 response.

#### Scenario: Verify valid credentials

- **WHEN** `verify_credentials()` is called with a valid URL pointing to a running SearXNG instance
- **THEN** the method returns `True`

#### Scenario: Verify invalid URL

- **WHEN** `verify_credentials()` is called with a URL that does not respond
- **THEN** the method returns `False`

#### Scenario: Verify with basic auth

- **WHEN** `verify_credentials()` is called with a URL, username, and password for a basic-auth-protected instance
- **THEN** the request includes an `Authorization: Basic` header and returns `True` if the instance accepts the credentials

### Requirement: SearXNG search method

The `search()` method SHALL accept `query` (str, required) and optional keyword arguments: `categories` (str), `time_range` (str: "day", "month", "year"), `language` (str), `safesearch` (int: 0, 1, 2), and `pageno` (int). The method SHALL send a GET request to `{url}/search?format=json&q={query}` with any additional parameters appended. If credentials include username/password, the request SHALL use HTTP Basic Auth. The method SHALL return a dict with keys: `query`, `results` (list of result dicts), `suggestions` (list of strings), and `number_of_results` (int).

#### Scenario: Basic search

- **WHEN** `search("python frameworks")` is called with valid credentials
- **THEN** the method returns a dict with `query`, `results`, `suggestions`, and `number_of_results` keys

#### Scenario: Search with filters

- **WHEN** `search("AI news", time_range="day", categories="news")` is called
- **THEN** the request includes `time_range=day` and `categories=news` query parameters

#### Scenario: Search result structure

- **WHEN** a search returns results
- **THEN** each result dict contains at minimum: `title` (str), `url` (str), `content` (str), `engines` (list of str), and `score` (float)

#### Scenario: Search with authentication

- **WHEN** `search()` is called and credentials include username and password
- **THEN** the HTTP request includes a Basic Auth header

#### Scenario: Search against unreachable instance

- **WHEN** `search()` is called and the SearXNG instance is unreachable
- **THEN** the method raises an exception with a descriptive error message

### Requirement: SearXNG default URL fallback

The `SearXNGPlatform` SHALL define a default URL of `https://search.errand.cloud`. When the `web_search` MCP tool is called and no credentials are stored for the SearXNG platform, the tool SHALL use this default URL without authentication.

#### Scenario: No credentials configured

- **WHEN** `web_search` is called and no SearXNG credentials exist in the database
- **THEN** the search is performed against `https://search.errand.cloud` without authentication

#### Scenario: Custom URL configured

- **WHEN** `web_search` is called and SearXNG credentials contain a custom URL
- **THEN** the search is performed against the custom URL

### Requirement: SearXNG platform registration

The backend SHALL register `SearXNGPlatform` in the platform registry during application startup, alongside existing platforms.

#### Scenario: SearXNG appears in platform list

- **WHEN** the application has started and an authenticated user requests `GET /api/platforms`
- **THEN** the response includes a platform with `id="searxng"` and `label="SearXNG Search"`
