# Tasks

- [x] Fix `mark_proxy_requests` middleware in `main.py`: change `request.state.__dict__[PROXY_REQUEST_MARKER] = True` to `setattr(request.state, PROXY_REQUEST_MARKER, True)`
- [x] Add test verifying that PROXY_REQUEST_MARKER set in middleware is readable from a route handler via `getattr(request.state, ...)`
- [x] Rebuild Docker Compose image and verify proxy requests return 200 instead of 401/403
