## Context

The worker (`backend/worker.py`) currently uses the Docker SDK to create, start, monitor, and clean up task-runner containers inside a DinD (Docker-in-Docker) sidecar. This is tightly coupled to Docker — every container operation (image pull, create, put_archive, start, logs, wait, remove) uses `docker.DockerClient` directly.

In production (K8s), the DinD sidecar runs privileged, which is a security concern. A planned macOS desktop app needs Apple Container support. Both cases require the worker to use a different container runtime without rewriting its core task-processing logic.

## Goals / Non-Goals

**Goals:**
- Abstract container runtime behind a clean interface so the worker's task-processing logic is runtime-agnostic
- Implement DockerRuntime (wrapping current Docker SDK code) as the default
- Implement KubernetesRuntime (K8s Jobs, ConfigMaps, pod log streaming) for production
- Eliminate the privileged DinD sidecar from the K8s deployment
- Enable a future AppleContainerRuntime (for the macOS app) without further refactoring
- Keep docker-compose local dev working exactly as today
- Preserve real-time log streaming to Valkey across all runtimes
- Preserve Playwright sidecar functionality

**Non-Goals:**
- Implementing the AppleContainerRuntime (that's the macOS app change)
- Changing the task-runner agent's core logic
- Changing how the worker dequeues or processes task results (only how it runs containers)
- Multi-worker scaling concerns (one task at a time per worker, unchanged)

## Decisions

### Decision 1: ContainerRuntime interface with three operations

**Choice**: A Python ABC with methods matching the worker's container lifecycle:

```
ContainerRuntime:
  prepare(image, env, files, output_dir) -> Handle
  run(handle) -> Iterator[str]      # streams log lines, blocks until exit
  result(handle) -> (exit_code, stdout, stderr)
  cleanup(handle)
```

- `prepare()` creates the container/Job, injects files, but doesn't start it
- `run()` starts execution and yields log lines in real-time (for Valkey publishing), blocks until the container exits
- `result()` retrieves the final exit code and captured output after run() completes
- `cleanup()` removes the container/Job and any temporary resources (ConfigMaps, etc.)

**Why**: This maps cleanly to the existing `process_task_in_container()` flow. The prepare/run/result/cleanup split isolates side effects and makes testing straightforward.

**Alternative considered**: A single `run_container()` that returns everything — but this can't support real-time log streaming.

### Decision 2: Runtime selected by CONTAINER_RUNTIME env var

**Choice**: `CONTAINER_RUNTIME` env var with values `docker` (default) or `kubernetes`. The runtime is instantiated once at worker startup.

**Why**: Simple, explicit, no auto-detection magic. Docker-compose sets nothing (gets default), Helm chart sets `kubernetes`, macOS app will set `apple` in the future.

### Decision 3: File-based output for runtime-agnostic result capture

**Choice**: The task-runner writes its structured JSON output to both stdout AND `/output/result.json`. Runtimes that can separate stdout/stderr (Docker) continue reading stdout. Runtimes that can't (K8s) read the file instead.

**Why**: The K8s pod log API merges stdout and stderr. Rather than adding in-band markers or changing the task-runner's output contract, writing to a file is a minimal, universal solution. The `/output` directory is created by the runtime (emptyDir in K8s, or just a directory in Docker).

### Decision 4: K8s file injection via ConfigMaps

**Choice**: The KubernetesRuntime creates a ConfigMap per task containing `prompt.txt`, `system_prompt.txt`, and `mcp.json`. The ConfigMap is mounted as a volume in the Job pod. Skills archives (potentially large) are handled via a secondary ConfigMap or an init container that pulls from a URL.

**Why**: ConfigMaps are the standard K8s mechanism for injecting configuration files. The 1MB size limit is adequate for prompts and MCP config. Skills could exceed this limit for large skill sets, but in practice the skill files are small text files.

**Alternative considered**: `kubectl cp` into running pod — requires the pod to be running and waiting, adds complexity. Init container — adds a second container to the "single container" Job, but could be acceptable for skills-only.

### Decision 5: Playwright networking in K8s

**Choice**: Playwright runs as a sidecar in the worker pod (not the task-runner Job). The worker discovers its own pod IP via the Kubernetes Downward API (`status.podIP`), and passes `PLAYWRIGHT_URL=http://<worker-pod-ip>:<port>/mcp` to the task-runner Job as an env var.

**Why**: Playwright is not multi-session capable — each worker needs its own instance. Keeping Playwright on the worker pod means one Playwright per worker, with exclusive access since workers process one task at a time. The task-runner Job connects over the cluster network.

**Alternative considered**: Playwright as a sidecar to the task-runner Job — violates the "single container Job" requirement and wastes startup time creating Playwright for every task.

### Decision 6: K8s log streaming via pod log API

**Choice**: The KubernetesRuntime streams logs using the Kubernetes Python client's `read_namespaced_pod_log(follow=True)`. The combined stdout+stderr stream is published to Valkey line-by-line (same as today). Since the real-time stream is for UI display, mixing stdout and stderr is acceptable.

The final structured output is read from `/output/result.json` (not from the log stream), so the mixing doesn't affect result parsing.

**Why**: Pod log follow is the standard K8s mechanism for real-time log access. It's reliable and well-supported by the Python client.

### Decision 7: Worker RBAC for K8s runtime

**Choice**: When `CONTAINER_RUNTIME=kubernetes`, the worker needs a ServiceAccount with RBAC permissions:
- `jobs.batch`: create, get, list, watch, delete
- `configmaps`: create, get, delete
- `pods`: get, list (for log streaming and pod IP discovery)
- `pods/log`: get (for log streaming)

All scoped to the worker's namespace.

**Why**: Least-privilege access. The worker only needs to manage Jobs and ConfigMaps in its own namespace.

## Risks / Trade-offs

**[ConfigMap size limit]** → ConfigMaps have a 1MB limit. Prompts and MCP config are well under this. Skills archives with many files could approach it. Mitigation: monitor skill sizes; if needed, switch to a PVC or init container for skills.

**[K8s Job cleanup]** → If the worker crashes after creating a Job but before cleanup, orphaned Jobs and ConfigMaps remain. Mitigation: use TTL-after-finished on Jobs (K8s feature); add a label selector so a recovering worker can find and clean up orphaned resources.

**[Network policy]** → Task-runner Jobs need network access to external APIs (LLM providers) and internal services (Playwright on worker pod, backend MCP). If the namespace has restrictive NetworkPolicies, these need to allow egress from task-runner pods. Mitigation: document required network access; add labels to task-runner pods for NetworkPolicy selection.

**[Dual output]** → Writing to both stdout and a file means the task-runner has two output paths. If the file write fails (disk full, permissions), stdout still works. The file is the primary path for K8s; stdout is primary for Docker. Both paths are simple and unlikely to diverge.

## Open Questions

None — the design is well-understood from the exploration discussion.
