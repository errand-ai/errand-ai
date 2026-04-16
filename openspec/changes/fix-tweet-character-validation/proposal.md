## Why

The `post_tweet` MCP tool uses naive `len(message)` to validate the 280-character limit, counting full URLs at their real length. Twitter automatically shortens all URLs to 23-character t.co links, so tweets with URLs are incorrectly rejected. This blocks the entire automated tweet-publishing workflow — all 9 approved tweets in the queue are being rejected despite being within Twitter's actual limit.

## What Changes

- Update the `post_tweet` tool's character validation to account for Twitter's t.co URL shortening (all URLs count as 23 characters regardless of actual length)
- Add tests for the new validation logic

## Capabilities

### New Capabilities
- `tweet-character-counting`: Validate tweet length using Twitter's actual counting rules (t.co URL shortening: all URLs count as 23 characters)

### Modified Capabilities

## Impact

- `errand/mcp_server.py`: `post_tweet` function — replace `len(message) > 280` with URL-aware character counting
- `errand/tests/test_mcp.py`: Add test cases for URL-containing tweets
- No API changes — the tool signature stays the same, it just validates more accurately
- No database or migration changes
