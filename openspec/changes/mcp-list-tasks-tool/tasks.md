## 1. Implementation

- [x] 1.1 Add `list_tasks` MCP tool function in `errand/mcp_server.py` — accept optional `status` parameter, query tasks excluding deleted/archived (or filter by status), return JSON array of `{id, title, status}`
- [x] 1.2 Validate the `status` parameter against board-visible statuses and return an error message for invalid values

## 2. Testing

- [x] 2.1 Add tests for `list_tasks` in `errand/tests/` — cover: no filter (returns board-visible tasks), status filter, invalid status, empty results
