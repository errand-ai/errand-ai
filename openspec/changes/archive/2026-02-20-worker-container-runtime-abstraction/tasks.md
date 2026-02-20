## 1. ContainerRuntime Interface

- [x] 1.1 Create `backend/container_runtime.py` with `ContainerRuntime` ABC defining `prepare`, `run`, `result`, `cleanup` methods
- [x] 1.2 Implement `DockerRuntime` by extracting current Docker SDK logic from `process_task_in_container()`
- [x] 1.3 Refactor `process_task_in_container()` to use the runtime interface instead of direct Docker calls
- [x] 1.4 Add runtime selection logic based on `CONTAINER_RUNTIME` env var in `run()`
- [x] 1.5 Verify docker-compose local dev still works end-to-end with DockerRuntime

## 2. Task-Runner File Output

- [x] 2.1 Update `task-runner/main.py` to write structured output to `/output/result.json` in addition to stdout (conditional on `/output` existing)
- [x] 2.2 Add task-runner tests for dual output (stdout + file)

## 3. KubernetesRuntime Implementation

- [x] 3.1 Add `kubernetes` Python package to `backend/requirements.txt`
- [x] 3.2 Implement `KubernetesRuntime.prepare()`: create ConfigMap with input files, create Job spec with ConfigMap volume mount and emptyDir at `/output`
- [x] 3.3 Implement `KubernetesRuntime.run()`: wait for pod to start, stream pod logs via `read_namespaced_pod_log(follow=True)`, yield lines
- [x] 3.4 Implement `KubernetesRuntime.result()`: get exit code from pod status, read `/output/result.json` from completed pod, read full pod logs as stderr
- [x] 3.5 Implement `KubernetesRuntime.cleanup()`: delete Job (with propagation) and ConfigMap
- [x] 3.6 Add Job labels (`managed-by`, `component`, `task-id`) and `ttlSecondsAfterFinished`
- [x] 3.7 Add orphaned Job cleanup on worker startup
- [x] 3.8 Handle Playwright URL injection: discover pod IP, pass `PLAYWRIGHT_URL` env var to Job

## 4. Helm Chart Changes

- [x] 4.1 Remove DinD sidecar container from worker Deployment template
- [x] 4.2 Add Playwright sidecar container to worker Deployment template
- [x] 4.3 Add `CONTAINER_RUNTIME=kubernetes` and `POD_IP` (Downward API) env vars to worker container
- [x] 4.4 Remove `DOCKER_HOST` env var and `privileged: true` from worker
- [x] 4.5 Create ServiceAccount, Role, and RoleBinding templates for the worker
- [x] 4.6 Add `playwright` values section (image, port, memoryLimit) and remove `dind` values section
- [x] 4.7 Remove `TASK_RUNNER_IMAGE` env var from worker (K8s runtime gets image from a config/env var directly)

## 5. Tests

- [x] 5.1 Add unit tests for ContainerRuntime interface and DockerRuntime
- [x] 5.2 Add unit tests for KubernetesRuntime (mocking K8s client)
- [x] 5.3 Verify existing worker tests pass with refactored code

## 6. Documentation

- [x] 6.1 Update `CLAUDE.md` to document `CONTAINER_RUNTIME` env var and K8s deployment changes
- [x] 6.2 Bump `VERSION` file
