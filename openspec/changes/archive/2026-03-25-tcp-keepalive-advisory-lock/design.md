## Context

The TaskManager holds a Postgres advisory lock via a sync `raw_connection()` for leader election. When a pod is killed without clean shutdown, the underlying TCP connection lingers in Postgres until OS-level TCP keepalive detects the dead peer. Default Linux TCP keepalive timeout is ~2 hours (7200s idle + 9 probes * 75s), and macOS is similar. During this time, the new pod cannot acquire the lock and silently stops processing tasks. The "waiting for lock" message is logged at DEBUG level, making the issue invisible in production logs.

## Goals / Non-Goals

**Goals:**
- Ensure stale advisory lock connections are detected by Postgres within ~30 seconds of pod death
- Make lock contention visible in production logs at INFO level

**Non-Goals:**
- Changing the leader election mechanism (advisory lock approach is sound)
- Adding application-level lock timeouts or lease TTLs
- Modifying the async database connections (only the sync leader lock connection is affected)

## Decisions

### Use libpq TCP keepalive connection parameters

PostgreSQL's libpq supports TCP keepalive via connection string parameters: `keepalives=1`, `keepalives_idle=10`, `keepalives_interval=10`, `keepalives_count=3`. These are passed through `create_sync_engine`'s `connect_args`. With idle=10s, interval=10s, count=3: if the remote end dies, Postgres detects it within ~40 seconds (10s idle + 3*10s probes). This is a well-supported, zero-dependency approach.

### Raise lock-wait log level to INFO

The "Another replica holds the leader lock, waiting..." message at DEBUG level made the 12-hour outage invisible. Changing to INFO provides visibility without being noisy — it only logs once per 5-second poll cycle when the lock is contended, which is an abnormal condition that operators should see.

## Risks / Trade-offs

- **More aggressive keepalive** means slightly more TCP overhead (keepalive probes every 10s after 10s idle). This is negligible for a single long-lived connection.
- **INFO-level lock logging** will produce log entries during normal rolling deployments (brief lock contention). This is acceptable — a few log lines during deploys is useful, not noisy.
