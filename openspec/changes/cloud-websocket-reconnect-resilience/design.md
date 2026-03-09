## Context

The `CloudWebSocketClient` in `errand/cloud_client.py` maintains a persistent WebSocket connection to errand-cloud. When errand-cloud performs a rolling deployment, the WebSocket connection is dropped. The client reconnects briefly, but the connection closes immediately (likely with close code 4001 — superseded). Because 4001 is in `NO_RECONNECT_CODES`, the client permanently stops, leaving the cloud UI broken until the errand-server is manually restarted.

The relevant code path:
1. `run()` loop calls `_connect_and_receive()`
2. Connection closes → `ConnectionClosedError` caught → `_handle_close(code, reason)` called
3. `_handle_close` with code 4001 sets `self._running = False`
4. `run()` loop sees `not self._running` and breaks — no reconnection

Additionally, the module-level `_ws_connected` flag and the cloud admin dashboard's Valkey `presence:{tenant_id}` key remain stale after the WebSocket dies, showing "connected" when it isn't.

## Goals / Non-Goals

**Goals:**
- Reconnect automatically after server-side deployments (rolling updates)
- Accurately reflect connection state when the WebSocket drops
- Detect dead connections (no ping/pong activity) and proactively reconnect

**Non-Goals:**
- Changing the errand-cloud eviction/presence mechanism
- Handling multi-replica load balancing
- Modifying the cloud UI's SSE retry behavior

## Decisions

### Decision 1: Reconnect on close code 4001 with backoff

**Choice**: Remove 4001 from `NO_RECONNECT_CODES`. When the connection is closed with 4001 (superseded), reconnect with exponential backoff instead of permanently stopping.

**Rationale**: Close code 4001 means "another instance took over", which is the expected behavior during server-side rolling deployments. During a deployment, the new pod sets presence and publishes an eviction, which closes the existing connection. The errand-server should reconnect to the newly deployed pod. Permanent shutdown was appropriate when the close came from a second errand-server instance connecting, but that scenario is indistinguishable from a deployment — and reconnection with backoff handles both correctly (the second instance will win again and re-evict).

**Alternative considered**: Adding a "deployment" close code to errand-cloud to distinguish from true supersession. Rejected because it requires coordinated changes to both repos and the simple reconnect handles both cases.

### Decision 2: Liveness watchdog via ping/pong timeout

**Choice**: Track the timestamp of the last received message (any type). If no message is received within a configurable window (e.g., 90 seconds — 3x the cloud's 30-second ping interval), proactively close the connection and trigger reconnection.

**Rationale**: A dead connection (TCP half-open) won't produce a close event. The WebSocket `async for` loop will block indefinitely. The cloud server sends pings every 30 seconds, so a 90-second silence reliably indicates a dead connection.

**Implementation**: Use `asyncio.wait_for` with a timeout on the message receive loop, or track `_last_message_time` and check it periodically.

### Decision 3: Immediate status cleanup on disconnect

**Choice**: In the `run()` loop, set `_ws_connected = False` and publish `cloud_status: disconnected` immediately when `_connect_and_receive()` returns or raises, before the backoff sleep.

**Rationale**: Currently `_ws_connected` is only cleared in specific paths. Any unexpected exit from `_connect_and_receive()` should reset the status so the UI reflects reality.

## Risks / Trade-offs

- **Reconnect storm after true supersession** → Mitigated by exponential backoff (max 30s). If a second errand-server genuinely took over, the first will reconnect, get evicted again, back off further, and eventually the backoff delay will be long enough for the situation to stabilize. The first instance should still stop after repeated evictions — add a max consecutive eviction count (e.g., 5) before stopping permanently.
- **Watchdog false positives** → 90-second timeout is 3x the ping interval, making false positives unlikely. If the cloud server changes its ping interval, this should be updated accordingly.
