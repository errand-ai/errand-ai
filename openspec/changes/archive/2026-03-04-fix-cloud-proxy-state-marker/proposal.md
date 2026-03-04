# Fix cloud proxy request state marker

## Problem

The `mark_proxy_requests` middleware in `main.py` uses `request.state.__dict__[PROXY_REQUEST_MARKER] = True` to mark requests that originate from the cloud WebSocket proxy handler. However, Starlette's `BaseHTTPMiddleware` creates different `State` wrapper objects in the middleware vs the route handler — both wrapping the same ASGI scope dict, but with separate Python `__dict__` attributes.

This means the marker set via `__dict__` in the middleware is invisible to `getattr(request.state, PROXY_REQUEST_MARKER, False)` in `_try_cloud_jwt_auth`, because `getattr` dispatches through `State.__getattr__` which reads from the shared ASGI scope `_state` dict, not the wrapper's `__dict__`.

As a result, cloud proxy requests always fall through to local auth (which fails with 401/403), making the entire remote UI proxy feature non-functional.

## Solution

Change `request.state.__dict__[PROXY_REQUEST_MARKER] = True` to `setattr(request.state, PROXY_REQUEST_MARKER, True)`. This writes to the shared ASGI scope state, making the marker visible to the route handler.

## Scope

- One-line fix in `main.py` middleware
- Add a test to verify the proxy auth flow works end-to-end
