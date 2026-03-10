# Tasks

## Cloud WebSocket Reconnect Resilience

- [x] Remove 4001 from `NO_RECONNECT_CODES` in `CloudWebSocketClient` and add a `_consecutive_evictions` counter. In `_handle_close`, when code is 4001, increment the counter and only set `self._running = False` when it reaches 5. Allow reconnection otherwise.
- [x] Reset `_consecutive_evictions` to 0 after a successful `register`/`registered` handshake in `_connect_and_receive` (after `_wait_for_registered` returns `True` and the connection is actively receiving messages).
- [x] Add liveness watchdog: track `_last_message_time = time.monotonic()` in `__init__`, update it on every received message in `_connect_and_receive`. Replace the `async for raw_message in ws` loop with `asyncio.wait_for(ws.recv(), timeout=90.0)` in a while loop, closing the connection on `asyncio.TimeoutError`.
- [x] Move the `_ws_connected = False` and `self._ws = None` assignments and the `cloud_status: disconnected` publish into the `run()` loop, immediately after `_connect_and_receive()` returns/raises and before the backoff sleep. Remove redundant status updates from `_handle_close`.
- [x] Add test: verify that a 4001 close code triggers reconnection (mock WebSocket that closes with 4001, assert `_running` is still `True` and `_backoff_attempt` increments).
- [x] Add test: verify that 5 consecutive 4001 closes cause permanent shutdown (`_running` becomes `False`).
- [x] Add test: verify the liveness watchdog closes the connection when no messages are received within 90 seconds (mock WebSocket recv that blocks indefinitely, assert connection is closed and reconnect is triggered).
- [x] Add test: verify `_ws_connected` is `False` and `cloud_status: disconnected` is published immediately after connection drop, before backoff sleep.
