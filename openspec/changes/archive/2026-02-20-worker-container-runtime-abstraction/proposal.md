## Why

The worker currently hard-codes Docker (via DinD) as the only way to run task-runner containers. This limits deployment options: the K8s deployment requires a privileged DinD sidecar (security concern), and a planned macOS desktop app needs Apple Container support. By abstracting the container runtime behind an interface, the worker can run task-runners via Docker (local dev), K8s Jobs (production), or Apple Container (macOS app) without changing its core logic.

Separately, using K8s Jobs instead of DinD for production eliminates the privileged sidecar, lets K8s schedule task-runners across the cluster, and is the idiomatic way to run ephemeral workloads on Kubernetes.

## What Changes

- **Container runtime abstraction**: New `ContainerRuntime` interface with `DockerRuntime` and `KubernetesRuntime` implementations; runtime selected by `CONTAINER_RUNTIME` env var
- **Task-runner file-based output**: Task-runner writes structured output to `/output/result.json` in addition to stdout, enabling runtimes that can't separate stdout/stderr (K8s)
- **K8s Job-based execution**: Worker creates K8s Jobs for task-runners, injects files via ConfigMaps, streams logs via K8s API, reads output from completed pods
- **Playwright stays on worker pod**: In K8s, Playwright remains a sidecar to the worker pod; task-runner Jobs connect to it via the worker pod's IP
- **BREAKING: DinD sidecar removed from K8s Helm chart**: Worker deployment no longer needs a privileged DinD container
- **Docker runtime unchanged**: docker-compose local dev continues using DinD exactly as today

## Capabilities

### New Capabilities
- `container-runtime`: Pluggable container runtime interface with Docker and Kubernetes implementations
- `k8s-task-execution`: Worker creates K8s Jobs for task-runners, manages ConfigMaps, streams logs, reads output

### Modified Capabilities
- `task-worker`: Runtime selection via env var; file injection and output capture delegated to runtime abstraction
- `task-runner-agent`: Additionally writes structured output to `/output/result.json`
- `helm-deployment`: DinD sidecar removed from worker; ServiceAccount RBAC for Jobs, ConfigMaps, pod logs added
- `local-dev-environment`: No change (docker-compose continues using DinD via DockerRuntime)

## Impact

- **Backend**: `worker.py` refactored — `process_task_in_container()` delegates to a `ContainerRuntime` implementation
- **Task-runner**: `main.py` writes output to both stdout and `/output/result.json`
- **Helm chart**: Worker deployment loses DinD sidecar and privileged security context; gains ServiceAccount with RBAC for Jobs/ConfigMaps/pods; Playwright becomes worker sidecar
- **Docker-compose**: Unchanged (DinD service stays for local dev)
- **New files**: `backend/container_runtime.py` (or similar) with interface + Docker + K8s implementations
- **Dependencies**: `kubernetes` Python package added to `requirements.txt` for K8s runtime
