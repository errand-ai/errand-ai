"""Container runtime abstraction for the worker.

Provides a pluggable interface for running task-runner containers via
Docker (local dev) or Kubernetes Jobs (production).
"""

import io
import logging
import os
import tarfile
import time
from abc import ABC, abstractmethod
from collections.abc import Iterator
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class RuntimeHandle:
    """Opaque handle returned by prepare(), passed to run/result/cleanup."""
    runtime_data: dict = field(default_factory=dict)


class ContainerRuntime(ABC):
    """Abstract base class for container runtime implementations."""

    @abstractmethod
    def prepare(
        self,
        image: str,
        env: dict[str, str],
        files: dict[str, str],
        output_dir: str | None = None,
        skills_tar: bytes | None = None,
        ssh_private_key: str | None = None,
        ssh_config: str | None = None,
    ) -> RuntimeHandle:
        """Create a container/Job and inject input files without starting execution.

        Args:
            image: Container image to run.
            env: Environment variables for the container.
            files: Dict of {filename: content} to inject at /workspace.
            output_dir: If set, mount an output directory at this path.
            skills_tar: Optional tar archive of skills to inject at /workspace.
            ssh_private_key: Optional SSH private key to inject.
            ssh_config: Optional SSH config to inject.

        Returns:
            A RuntimeHandle to pass to run(), result(), and cleanup().
        """

    @abstractmethod
    def run(self, handle: RuntimeHandle) -> Iterator[str]:
        """Start execution and yield log lines in real-time.

        Blocks until the container exits. Each yielded string is a single
        log line (without trailing newline).
        """

    @abstractmethod
    def result(self, handle: RuntimeHandle) -> tuple[int, str, str]:
        """Retrieve exit code and captured output after run() completes.

        Returns:
            (exit_code, stdout, stderr) tuple.
        """

    @abstractmethod
    def cleanup(self, handle: RuntimeHandle) -> None:
        """Remove the container/Job and any temporary resources."""


# ---------------------------------------------------------------------------
# DockerRuntime
# ---------------------------------------------------------------------------


def _put_archive(container: Any, files: dict[str, str], dest: str = "/workspace") -> None:
    """Create a tar archive from {filename: content} and copy into container."""
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w") as tar:
        for name, content in files.items():
            data = content.encode("utf-8")
            info = tarfile.TarInfo(name=name)
            info.size = len(data)
            tar.addfile(info, io.BytesIO(data))
    buf.seek(0)
    container.put_archive(dest, buf)


def _put_archive_ssh(container: Any, private_key: str, ssh_config: str) -> None:
    """Copy SSH private key and config into the container's ~/.ssh/ directory."""
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w") as tar:
        ssh_dir = tarfile.TarInfo(name=".")
        ssh_dir.type = tarfile.DIRTYPE
        ssh_dir.mode = 0o700
        ssh_dir.uid = 65532
        ssh_dir.gid = 65532
        tar.addfile(ssh_dir)

        key_data = private_key.encode("utf-8")
        key_info = tarfile.TarInfo(name="id_rsa.agent")
        key_info.size = len(key_data)
        key_info.mode = 0o600
        key_info.uid = 65532
        key_info.gid = 65532
        tar.addfile(key_info, io.BytesIO(key_data))

        config_data = ssh_config.encode("utf-8")
        config_info = tarfile.TarInfo(name="config")
        config_info.size = len(config_data)
        config_info.mode = 0o644
        config_info.uid = 65532
        config_info.gid = 65532
        tar.addfile(config_info, io.BytesIO(config_data))
    buf.seek(0)
    container.put_archive("/home/nonroot/.ssh", buf)


class DockerRuntime(ContainerRuntime):
    """Runs task-runner containers via the Docker SDK (DinD)."""

    def __init__(self, client: Any) -> None:
        self.client = client

    def prepare(
        self,
        image: str,
        env: dict[str, str],
        files: dict[str, str],
        output_dir: str | None = None,
        skills_tar: bytes | None = None,
        ssh_private_key: str | None = None,
        ssh_config: str | None = None,
    ) -> RuntimeHandle:
        from docker.errors import ImageNotFound

        # Ensure image is available
        try:
            self.client.images.get(image)
            logger.info("Image %s found locally", image)
        except ImageNotFound:
            logger.info("Image %s not found locally, pulling...", image)
            self.client.images.pull(image)

        container = self.client.containers.create(
            image=image,
            environment=env,
            network_mode="host",
            detach=True,
        )
        logger.info("Created Docker container %s", container.short_id)

        # Inject workspace files
        _put_archive(container, files)

        # Inject skills if provided
        if skills_tar:
            container.put_archive("/workspace", io.BytesIO(skills_tar))

        # Inject SSH credentials if provided
        if ssh_private_key and ssh_config:
            _put_archive_ssh(container, ssh_private_key, ssh_config)

        return RuntimeHandle(runtime_data={"container": container})

    def run(self, handle: RuntimeHandle) -> Iterator[str]:
        container = handle.runtime_data["container"]
        container.start()

        buf = ""
        for chunk in container.logs(stream=True, follow=True, stderr=True, stdout=False):
            buf += chunk.decode("utf-8", errors="replace")
            while "\n" in buf:
                line, buf = buf.split("\n", 1)
                if line:
                    yield line
        # Flush remaining
        if buf.strip():
            yield buf.strip()

    def result(self, handle: RuntimeHandle) -> tuple[int, str, str]:
        container = handle.runtime_data["container"]
        wait_result = container.wait()
        exit_code = wait_result.get("StatusCode", -1)
        stdout = container.logs(stdout=True, stderr=False).decode("utf-8", errors="replace")
        stderr = container.logs(stdout=False, stderr=True).decode("utf-8", errors="replace")
        return exit_code, stdout, stderr

    def cleanup(self, handle: RuntimeHandle) -> None:
        container = handle.runtime_data.get("container")
        if container is not None:
            try:
                container.remove(force=True)
                logger.info("Removed Docker container %s", container.short_id)
            except Exception:
                logger.debug("Failed to remove Docker container", exc_info=True)


# ---------------------------------------------------------------------------
# KubernetesRuntime
# ---------------------------------------------------------------------------

# Default TTL for completed Jobs (seconds) — orphan protection
K8S_JOB_TTL_SECONDS = 300
K8S_POD_START_TIMEOUT = 300  # seconds to wait for pod to start


def _read_namespace() -> str:
    """Read the K8s namespace from env var or service account mount."""
    ns = os.environ.get("TASK_RUNNER_NAMESPACE")
    if ns:
        return ns
    try:
        with open("/var/run/secrets/kubernetes.io/serviceaccount/namespace") as f:
            return f.read().strip()
    except OSError:
        return "default"


class KubernetesRuntime(ContainerRuntime):
    """Runs task-runner containers as Kubernetes Jobs."""

    def __init__(self) -> None:
        from kubernetes import client, config

        try:
            config.load_incluster_config()
        except config.ConfigException:
            config.load_kube_config()

        self.core_v1 = client.CoreV1Api()
        self.batch_v1 = client.BatchV1Api()
        self.namespace = _read_namespace()
        self.task_runner_image = os.environ.get("TASK_RUNNER_IMAGE", "errand-task-runner:latest")
        logger.info("KubernetesRuntime initialised (namespace=%s)", self.namespace)

    def prepare(
        self,
        image: str,
        env: dict[str, str],
        files: dict[str, str],
        output_dir: str | None = None,
        skills_tar: bytes | None = None,
        ssh_private_key: str | None = None,
        ssh_config: str | None = None,
    ) -> RuntimeHandle:
        from kubernetes import client

        import uuid
        job_id = str(uuid.uuid4())[:8]
        task_id = env.get("_TASK_ID", job_id)
        configmap_name = f"task-runner-{job_id}"
        job_name = f"task-runner-{job_id}"

        # Create ConfigMap with input files
        configmap = client.V1ConfigMap(
            metadata=client.V1ObjectMeta(
                name=configmap_name,
                namespace=self.namespace,
                labels={
                    "app.kubernetes.io/managed-by": "content-manager-worker",
                    "app.kubernetes.io/component": "task-runner",
                    "content-manager/task-id": str(task_id),
                },
            ),
            data=files,
        )
        self.core_v1.create_namespaced_config_map(self.namespace, configmap)
        logger.info("Created ConfigMap %s", configmap_name)

        # Build env vars list
        env_list = [
            client.V1EnvVar(name=k, value=v)
            for k, v in env.items()
            if not k.startswith("_")  # skip internal keys like _TASK_ID
        ]

        # Playwright URL injection
        pod_ip = os.environ.get("POD_IP", "")
        playwright_port = os.environ.get("PLAYWRIGHT_PORT", "")
        playwright_image = os.environ.get("PLAYWRIGHT_MCP_IMAGE", "")
        if pod_ip and playwright_port and playwright_image:
            env_list.append(
                client.V1EnvVar(
                    name="PLAYWRIGHT_URL",
                    value=f"http://{pod_ip}:{playwright_port}/mcp",
                )
            )

        # Volume mounts
        volume_mounts = [
            client.V1VolumeMount(name="workspace", mount_path="/workspace"),
            client.V1VolumeMount(name="output", mount_path="/output"),
        ]

        # Volumes
        volumes = [
            client.V1Volume(
                name="workspace",
                config_map=client.V1ConfigMapVolumeSource(name=configmap_name),
            ),
            client.V1Volume(
                name="output",
                empty_dir=client.V1EmptyDirVolumeSource(),
            ),
        ]

        # Build Job spec
        job = client.V1Job(
            metadata=client.V1ObjectMeta(
                name=job_name,
                namespace=self.namespace,
                labels={
                    "app.kubernetes.io/managed-by": "content-manager-worker",
                    "app.kubernetes.io/component": "task-runner",
                    "content-manager/task-id": str(task_id),
                },
            ),
            spec=client.V1JobSpec(
                ttl_seconds_after_finished=K8S_JOB_TTL_SECONDS,
                backoff_limit=0,
                template=client.V1PodTemplateSpec(
                    metadata=client.V1ObjectMeta(
                        labels={
                            "app.kubernetes.io/managed-by": "content-manager-worker",
                            "app.kubernetes.io/component": "task-runner",
                            "content-manager/task-id": str(task_id),
                        },
                    ),
                    spec=client.V1PodSpec(
                        restart_policy="Never",
                        containers=[
                            client.V1Container(
                                name="task-runner",
                                image=image,
                                env=env_list,
                                volume_mounts=volume_mounts,
                            ),
                        ],
                        volumes=volumes,
                    ),
                ),
            ),
        )

        self.batch_v1.create_namespaced_job(self.namespace, job)
        logger.info("Created Job %s", job_name)

        return RuntimeHandle(runtime_data={
            "job_name": job_name,
            "configmap_name": configmap_name,
            "namespace": self.namespace,
            "task_id": task_id,
        })

    def _wait_for_pod(self, job_name: str) -> str:
        """Wait for the Job's pod to be running/succeeded/failed. Returns pod name."""
        # Note: uses self.core_v1 (already initialised) — no local imports needed

        label_selector = f"job-name={job_name}"
        deadline = time.time() + K8S_POD_START_TIMEOUT

        while time.time() < deadline:
            pods = self.core_v1.list_namespaced_pod(
                self.namespace, label_selector=label_selector
            )
            for pod in pods.items:
                phase = pod.status.phase
                if phase in ("Running", "Succeeded", "Failed"):
                    return pod.metadata.name
            time.sleep(2)

        raise TimeoutError(f"Pod for job {job_name} did not start within {K8S_POD_START_TIMEOUT}s")

    def run(self, handle: RuntimeHandle) -> Iterator[str]:
        job_name = handle.runtime_data["job_name"]
        namespace = handle.runtime_data["namespace"]

        pod_name = self._wait_for_pod(job_name)
        handle.runtime_data["pod_name"] = pod_name
        logger.info("Streaming logs from pod %s", pod_name)

        # Stream logs — follow=True blocks until pod exits
        log_stream = self.core_v1.read_namespaced_pod_log(
            pod_name,
            namespace,
            follow=True,
            _preload_content=False,
        )

        buf = ""
        for chunk in log_stream:
            if isinstance(chunk, bytes):
                chunk = chunk.decode("utf-8", errors="replace")
            buf += chunk
            while "\n" in buf:
                line, buf = buf.split("\n", 1)
                if line:
                    yield line
        if buf.strip():
            yield buf.strip()

    def result(self, handle: RuntimeHandle) -> tuple[int, str, str]:
        from kubernetes.client.rest import ApiException
        from kubernetes.stream import stream as k8s_stream

        pod_name = handle.runtime_data.get("pod_name", "")
        namespace = handle.runtime_data["namespace"]

        # Get exit code from pod status
        exit_code = -1
        try:
            pod = self.core_v1.read_namespaced_pod(pod_name, namespace)
            for cs in (pod.status.container_statuses or []):
                if cs.name == "task-runner" and cs.state and cs.state.terminated:
                    exit_code = cs.state.terminated.exit_code
                    break
        except ApiException:
            logger.warning("Failed to read pod status for %s", pod_name, exc_info=True)

        # Get full logs (combined stdout+stderr from the pod)
        full_logs = ""
        try:
            full_logs = self.core_v1.read_namespaced_pod_log(pod_name, namespace)
        except ApiException:
            logger.warning("Failed to read logs from pod %s", pod_name, exc_info=True)

        # Try to read /output/result.json via exec (preferred — clean structured output)
        stdout = ""
        try:
            resp = k8s_stream(
                self.core_v1.connect_get_namespaced_pod_exec,
                pod_name,
                namespace,
                command=["cat", "/output/result.json"],
                container="task-runner",
                stderr=False,
                stdin=False,
                stdout=True,
                tty=False,
            )
            stdout = resp if isinstance(resp, str) else resp.decode("utf-8", errors="replace")
        except ApiException:
            logger.warning("Failed to read /output/result.json from pod %s", pod_name, exc_info=True)

        # Fallback: if exec failed, extract the JSON from pod logs.
        # The task-runner prints the JSON as the last stdout line; in K8s logs
        # stdout and stderr are merged but the JSON is recognisable by structure.
        if not stdout and full_logs:
            for line in reversed(full_logs.splitlines()):
                stripped = line.strip()
                if stripped.startswith("{") and stripped.endswith("}"):
                    try:
                        import json
                        obj = json.loads(stripped)
                        if "status" in obj and "result" in obj:
                            stdout = stripped
                            logger.info("Extracted structured output from pod logs (exec fallback)")
                            break
                    except (json.JSONDecodeError, KeyError):
                        continue

        return exit_code, stdout, full_logs

    def cleanup(self, handle: RuntimeHandle) -> None:
        from kubernetes.client.rest import ApiException

        job_name = handle.runtime_data.get("job_name", "")
        configmap_name = handle.runtime_data.get("configmap_name", "")
        namespace = handle.runtime_data.get("namespace", self.namespace)

        if job_name:
            try:
                self.batch_v1.delete_namespaced_job(
                    job_name,
                    namespace,
                    propagation_policy="Foreground",
                )
                logger.info("Deleted Job %s", job_name)
            except ApiException:
                logger.debug("Failed to delete Job %s", job_name, exc_info=True)

        if configmap_name:
            try:
                self.core_v1.delete_namespaced_config_map(configmap_name, namespace)
                logger.info("Deleted ConfigMap %s", configmap_name)
            except ApiException:
                logger.debug("Failed to delete ConfigMap %s", configmap_name, exc_info=True)


def cleanup_orphaned_jobs(runtime: KubernetesRuntime) -> None:
    """Clean up orphaned task-runner Jobs and ConfigMaps on worker startup."""
    from kubernetes.client.rest import ApiException

    label_selector = "app.kubernetes.io/managed-by=content-manager-worker"
    try:
        jobs = runtime.batch_v1.list_namespaced_job(
            runtime.namespace, label_selector=label_selector
        )
        for job in jobs.items:
            name = job.metadata.name
            logger.info("Cleaning up orphaned Job %s", name)
            try:
                runtime.batch_v1.delete_namespaced_job(
                    name, runtime.namespace, propagation_policy="Foreground"
                )
            except ApiException:
                logger.debug("Failed to delete orphaned Job %s", name, exc_info=True)

        # Clean up orphaned ConfigMaps
        configmaps = runtime.core_v1.list_namespaced_config_map(
            runtime.namespace, label_selector=label_selector
        )
        for cm in configmaps.items:
            name = cm.metadata.name
            logger.info("Cleaning up orphaned ConfigMap %s", name)
            try:
                runtime.core_v1.delete_namespaced_config_map(name, runtime.namespace)
            except ApiException:
                logger.debug("Failed to delete orphaned ConfigMap %s", name, exc_info=True)
    except ApiException:
        logger.warning("Failed to list orphaned resources", exc_info=True)


def create_runtime(runtime_type: str | None = None) -> ContainerRuntime:
    """Factory function to create the appropriate runtime based on CONTAINER_RUNTIME env var."""
    runtime_type = runtime_type or os.environ.get("CONTAINER_RUNTIME", "docker")

    if runtime_type == "docker":
        import docker
        from docker.errors import DockerException

        docker_host = os.environ.get("DOCKER_HOST", "")
        kwargs = {}
        if docker_host:
            kwargs["base_url"] = docker_host

        delay = 1.0
        max_delay = 30.0
        while True:
            try:
                client = docker.DockerClient(**kwargs)
                client.ping()
                logger.info("Connected to Docker daemon")
                return DockerRuntime(client)
            except DockerException as e:
                logger.warning("Docker not ready (%.1fs backoff): %s", delay, e)
                time.sleep(delay)
                delay = min(delay * 2, max_delay)

    elif runtime_type == "kubernetes":
        runtime = KubernetesRuntime()
        cleanup_orphaned_jobs(runtime)
        return runtime

    else:
        raise ValueError(f"Unknown CONTAINER_RUNTIME: {runtime_type!r} (expected 'docker' or 'kubernetes')")
