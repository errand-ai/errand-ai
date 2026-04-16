## 1. Core Implementation

- [x] 1.1 Add `TWITTER_TCO_URL_LENGTH = 23` constant and `twitter_character_count(text: str) -> int` helper function to `errand/mcp_server.py` that replaces URL lengths with 23 characters using `re.findall(r'https?://\S+', text)`
- [x] 1.2 Update `post_tweet` in `errand/mcp_server.py` to use `twitter_character_count()` instead of `len(message)` for the 280-character validation

## 2. Tests

- [x] 2.1 Add unit tests for `twitter_character_count()`: tweet with single URL within limit, tweet with URL over limit, tweet with multiple URLs, tweet without URLs, tweet without URLs over limit
- [x] 2.2 Add integration test for `post_tweet` tool: verify a tweet with a long URL but short body text passes validation (previously would have been rejected)
- [x] 2.3 Run full test suite to confirm no regressions
