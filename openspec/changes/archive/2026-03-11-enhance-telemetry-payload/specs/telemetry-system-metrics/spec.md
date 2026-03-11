## ADDED Requirements

### Requirement: CPU count collection
The telemetry module SHALL collect the logical CPU count using psutil.

#### Scenario: CPU count available
- **WHEN** the telemetry system info is collected
- **THEN** `system.cpu_count` SHALL be set to the logical CPU count as reported by `psutil.cpu_count(logical=True)`

#### Scenario: CPU count unavailable
- **WHEN** psutil cannot determine the CPU count (returns None)
- **THEN** `system.cpu_count` SHALL be `null`

### Requirement: Host memory collection
The telemetry module SHALL collect total and available host memory using psutil.

#### Scenario: Memory metrics collected
- **WHEN** the telemetry system info is collected
- **THEN** `system.memory_total_mb` SHALL be set to the total physical memory in megabytes (integer, rounded down)
- **AND** `system.memory_available_mb` SHALL be set to the currently available memory in megabytes (integer, rounded down)

### Requirement: Container memory limit detection
The telemetry module SHALL detect container memory limits from cgroup files.

#### Scenario: Cgroup v2 memory limit
- **WHEN** the file `/sys/fs/cgroup/memory.max` exists and contains a numeric value
- **THEN** `system.container_memory_limit_mb` SHALL be set to that value converted to megabytes (integer, rounded down)

#### Scenario: Cgroup v2 unlimited memory
- **WHEN** the file `/sys/fs/cgroup/memory.max` exists and contains `max`
- **THEN** `system.container_memory_limit_mb` SHALL be `null`

#### Scenario: Cgroup v1 memory limit
- **WHEN** `/sys/fs/cgroup/memory.max` does not exist and `/sys/fs/cgroup/memory/memory.limit_in_bytes` exists with a numeric value less than the total host memory
- **THEN** `system.container_memory_limit_mb` SHALL be set to that value converted to megabytes

#### Scenario: No cgroup memory limit detected
- **WHEN** neither cgroup v2 nor v1 memory limit files are readable
- **THEN** `system.container_memory_limit_mb` SHALL be `null`

### Requirement: Container CPU limit detection
The telemetry module SHALL detect container CPU limits from cgroup files.

#### Scenario: Cgroup v2 CPU limit
- **WHEN** the file `/sys/fs/cgroup/cpu.max` exists and contains `<quota> <period>` where quota is numeric
- **THEN** `system.container_cpu_limit` SHALL be set to `quota / period` as a float (e.g., `2.0` for 2 CPUs)

#### Scenario: Cgroup v2 unlimited CPU
- **WHEN** the file `/sys/fs/cgroup/cpu.max` exists and the quota is `max`
- **THEN** `system.container_cpu_limit` SHALL be `null`

#### Scenario: Cgroup v1 CPU limit
- **WHEN** `/sys/fs/cgroup/cpu.max` does not exist and `/sys/fs/cgroup/cpu/cpu.cfs_quota_us` exists with a positive value
- **THEN** `system.container_cpu_limit` SHALL be set to `cfs_quota_us / cfs_period_us` as a float
- **AND** `cfs_period_us` SHALL be read from `/sys/fs/cgroup/cpu/cpu.cfs_period_us` (defaults to 100000 if unreadable)

#### Scenario: Cgroup v1 unlimited CPU
- **WHEN** `/sys/fs/cgroup/cpu/cpu.cfs_quota_us` contains `-1`
- **THEN** `system.container_cpu_limit` SHALL be `null`

#### Scenario: No cgroup CPU limit detected
- **WHEN** neither cgroup v2 nor v1 CPU limit files are readable
- **THEN** `system.container_cpu_limit` SHALL be `null`

### Requirement: Disk space collection
The telemetry module SHALL collect available disk space using psutil.

#### Scenario: Disk space available
- **WHEN** the telemetry system info is collected
- **THEN** `system.disk_available_mb` SHALL be set to the available disk space on the root filesystem (`/`) in megabytes (integer, rounded down)

### Requirement: Static system info caching
Static system metrics (CPU count, total memory, container limits) SHALL be collected once and cached for the lifetime of the process.

#### Scenario: First collection caches results
- **WHEN** system info is collected for the first time
- **THEN** the static values SHALL be cached at module level

#### Scenario: Subsequent collections reuse cache
- **WHEN** system info is collected on subsequent report cycles
- **THEN** the cached static values SHALL be reused and only dynamic values (available memory, disk) SHALL be re-read
