# Cloud WebSocket Reconnect Resilience

## Problem

When errand-cloud deploys a new version (rolling update), the errand-server's WebSocket connection is dropped. The errand-server reconnects, but the connection immediately closes again. After this, the errand-server stops attempting to reconnect entirely, leaving the cloud UI unable to display tasks or proxy requests — despite the admin dashboard showing the server as "connected" (stale presence data in Valkey).

### Root Cause Analysis

Investigation on the `devops-consultants` cluster revealed:

1. **Presence key exists but capabilities key is missing** — The `presence:{tenant_id}` key in Valkey was set during the brief reconnection, but `capabilities:{tenant_id}` was never set because the WebSocket closed before the `register`/`registered` handshake completed.

2. **Immediate close after connect** — The errand-cloud logs show `WebSocket /ws [accepted]` → `connection open` → `connection closed` with no messages exchanged. The register handshake never completed.

3. **No reconnection after close** — The errand-server's `CloudWebSocketClient` has `NO_RECONNECT_CODES = {4001, 4003}`. If the close code is 4001 (superseded — e.g., from the rolling update's eviction mechanism), `self._running` is set to `False` and the client permanently stops.

4. **Stale "connected" status** — The errand-server's internal `_ws_connected` flag and the cloud admin dashboard's presence check both show "connected" even though the WebSocket is dead.

### Impact

- Cloud UI task board is empty (all `/api/proxy/events` calls return 502)
- Browser SSE EventSource auto-retries on 502, flooding the server with requests
- Only fix is manually restarting the errand-server

## Proposed Solution

Make the WebSocket client resilient to server-side deployments by:

1. **Always reconnect on unexpected close** — Close code 4001 (superseded) during a server deployment should trigger reconnection, not permanent shutdown. Only stop permanently for 4003 (tenant disabled) or repeated auth failures.

2. **Add a liveness watchdog** — If no messages (including pings) are received within a timeout window, proactively close and reconnect rather than sitting on a dead connection.

3. **Clear stale status on close** — When the WebSocket closes unexpectedly, immediately update `_ws_connected` and publish a `cloud_status: disconnected` event so the UI accurately reflects the connection state.

## Non-goals

- Changing the errand-cloud side eviction/presence mechanism
- Handling multi-replica load balancing (separate concern)
- Modifying the SSE relay retry behavior in the cloud UI
