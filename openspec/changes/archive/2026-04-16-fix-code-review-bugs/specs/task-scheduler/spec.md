## MODIFIED Requirements

### Requirement: Valkey distributed lock ensures single scheduler instance
The scheduler SHALL acquire a Valkey distributed lock before checking for due tasks. The lock SHALL use the `SET key value NX EX ttl` pattern with key `errand:scheduler-lock`, a TTL of 30 seconds, and the pod hostname as the lock value. If lock acquisition fails (another replica holds the lock), the scheduler SHALL skip the cycle and sleep until the next interval. The lock SHALL be refreshed every cycle while held.

When releasing the lock, the scheduler SHALL use an atomic Lua script that checks the lock value matches the current holder's identity before deleting. If the lock value no longer matches (i.e. another replica has acquired it after expiry), the release SHALL be a no-op. This prevents a replica from releasing a lock it no longer owns.

#### Scenario: First replica acquires the lock and runs scheduler
- **WHEN** a single backend replica starts and no lock exists in Valkey
- **THEN** the replica acquires the lock and runs the scheduler check

#### Scenario: Second replica fails to acquire lock and skips
- **WHEN** two backend replicas are running and the first holds the lock
- **THEN** the second replica's `SET NX` returns false and it skips the scheduler cycle

#### Scenario: Lock expires and another replica takes over
- **WHEN** the lock-holding replica crashes and the lock TTL expires
- **THEN** another replica acquires the lock on its next cycle and resumes scheduling

#### Scenario: Lock is refreshed each cycle
- **WHEN** the lock-holding replica completes a scheduler cycle
- **THEN** it refreshes the lock TTL back to 30 seconds before sleeping

#### Scenario: Lock released only if still owned by this holder
- **WHEN** the original lock holder calls release and the lock value still matches its identity
- **THEN** the Lua script deletes the key atomically

#### Scenario: Lock not released if owned by another replica
- **WHEN** the lock TTL expired and a second replica acquired the lock, then the original replica attempts to release
- **THEN** the Lua script finds the lock value does not match and performs no delete
