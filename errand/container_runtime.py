"""Container runtime abstraction for the worker and task manager.

Provides a pluggable interface for running task-runner containers via
Docker (local dev), Kubernetes Jobs (production), or the macOS desktop
app bridge API (Apple Containerization).
"""

import asyncio
import base64
import io
import logging
import os
import tarfile
import time
from abc import ABC, abstractmethod
from collections.abc import AsyncIterator, Iterator
from dataclasses import dataclass, field
from typing import Any

import requests

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
        ssh_hosts: list[str] | None = None,
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
            ssh_hosts: Optional list of SSH hosts to pre-populate known_hosts.

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

    # -- Async interface (default: wrap sync methods via run_in_executor) ----

    async def async_prepare(
        self,
        image: str,
        env: dict[str, str],
        files: dict[str, str],
        output_dir: str | None = None,
        skills_tar: bytes | None = None,
        ssh_private_key: str | None = None,
        ssh_config: str | None = None,
        ssh_hosts: list[str] | None = None,
    ) -> RuntimeHandle:
        """Async version of prepare(). Default wraps sync via executor."""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            None,
            lambda: self.prepare(
                image, env, files, output_dir, skills_tar,
                ssh_private_key, ssh_config, ssh_hosts,
            ),
        )

    async def async_run(self, handle: RuntimeHandle) -> AsyncIterator[str]:
        """Async version of run(). Default wraps sync iterator via executor."""
        loop = asyncio.get_event_loop()
        # Run the sync iterator in a thread and feed lines through a queue
        queue: asyncio.Queue[str | None] = asyncio.Queue()

        def _stream():
            try:
                for line in self.run(handle):
                    loop.call_soon_threadsafe(queue.put_nowait, line)
            finally:
                loop.call_soon_threadsafe(queue.put_nowait, None)

        task = loop.run_in_executor(None, _stream)
        try:
            while True:
                item = await queue.get()
                if item is None:
                    break
                yield item
        finally:
            await task

    async def async_result(self, handle: RuntimeHandle) -> tuple[int, str, str]:
        """Async version of result(). Default wraps sync via executor."""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self.result, handle)

    async def async_cleanup(self, handle: RuntimeHandle) -> None:
        """Async version of cleanup(). Default wraps sync via executor."""
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, self.cleanup, handle)


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
        ssh_hosts: list[str] | None = None,
    ) -> RuntimeHandle:
        from docker.errors import ImageNotFound

        # Ensure image is available
        try:
            self.client.images.get(image)
            logger.info("Image %s found locally", image)
        except ImageNotFound:
            logger.info("Image %s not found locally, pulling...", image)
            self.client.images.pull(image)

        # Support named network via TASK_RUNNER_NETWORK env var;
        # fall back to network_mode="host" for backward compat.
        task_runner_network = os.environ.get("TASK_RUNNER_NETWORK", "")
        net_kwargs: dict[str, Any] = {}
        if task_runner_network:
            net_kwargs["network"] = task_runner_network
        else:
            net_kwargs["network_mode"] = "host"

        container = self.client.containers.create(
            image=image,
            environment=env,
            detach=True,
            **net_kwargs,
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
        ssh_hosts: list[str] | None = None,
    ) -> RuntimeHandle:
        from kubernetes import client

        import uuid
        job_id = str(uuid.uuid4())[:8]
        task_id = env.get("_TASK_ID", job_id)
        configmap_name = f"task-runner-{job_id}"
        job_name = f"task-runner-{job_id}"

        # Create ConfigMap with workspace text files; skills tar goes in binaryData.
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
            binary_data={"skills.tar": base64.b64encode(skills_tar).decode("ascii")} if skills_tar else None,
        )
        self.core_v1.create_namespaced_config_map(self.namespace, configmap)
        logger.info("Created ConfigMap %s", configmap_name)

        # Create Secret for SSH credentials if provided
        secret_name = ""
        if ssh_private_key and ssh_config:
            secret_name = f"task-runner-ssh-{job_id}"
            secret = client.V1Secret(
                metadata=client.V1ObjectMeta(
                    name=secret_name,
                    namespace=self.namespace,
                    labels={
                        "app.kubernetes.io/managed-by": "content-manager-worker",
                        "app.kubernetes.io/component": "task-runner",
                        "content-manager/task-id": str(task_id),
                    },
                ),
                string_data={
                    "id_rsa.agent": ssh_private_key,
                    "config": ssh_config,
                },
            )
            self.core_v1.create_namespaced_secret(self.namespace, secret)
            logger.info("Created Secret %s for SSH credentials", secret_name)

        # Build env vars list
        env_list = [
            client.V1EnvVar(name=k, value=v)
            for k, v in env.items()
            if not k.startswith("_")  # skip internal keys like _TASK_ID
        ]

        # Volume mounts for main container
        volume_mounts = [
            client.V1VolumeMount(name="workspace", mount_path="/workspace"),
            client.V1VolumeMount(name="output", mount_path="/output"),
        ]

        # Volumes: workspace is emptyDir (populated by init container),
        # config is the read-only ConfigMap.
        volumes = [
            client.V1Volume(
                name="workspace",
                empty_dir=client.V1EmptyDirVolumeSource(),
            ),
            client.V1Volume(
                name="config",
                config_map=client.V1ConfigMapVolumeSource(name=configmap_name),
            ),
            client.V1Volume(
                name="output",
                empty_dir=client.V1EmptyDirVolumeSource(),
            ),
        ]

        # Init container: copy workspace files from ConfigMap and extract
        # skills tar (if present) into the writable emptyDir workspace.
        # K8s ConfigMap volumes mount entries as symlinks (prompt.txt -> ..data/prompt.txt),
        # so use `find -L` to follow them. Exclude dotfiles (..data, timestamp dirs).
        init_cmd = (
            "find -L /config -maxdepth 1 -type f ! -name 'skills.tar' ! -name '.*' "
            "-exec cp {} /workspace/ \\;"
        )
        if skills_tar:
            init_cmd += " && tar xf /config/skills.tar -C /workspace/"

        init_volume_mounts = [
            client.V1VolumeMount(name="config", mount_path="/config", read_only=True),
            client.V1VolumeMount(name="workspace", mount_path="/workspace"),
        ]

        # SSH credentials: K8s Secret volumes are always owned by root, but the
        # task-runner runs as nonroot (UID 65532). Mount the Secret into the init
        # container and copy with correct ownership to a shared emptyDir.
        ssh_mount_path = "/home/nonroot/.ssh"
        if secret_name:
            volumes.append(
                client.V1Volume(
                    name="ssh-secret",
                    secret=client.V1SecretVolumeSource(secret_name=secret_name),
                )
            )
            volumes.append(
                client.V1Volume(
                    name="ssh-credentials",
                    empty_dir=client.V1EmptyDirVolumeSource(),
                )
            )
            init_volume_mounts.extend([
                client.V1VolumeMount(name="ssh-secret", mount_path="/ssh-secret", read_only=True),
                client.V1VolumeMount(name="ssh-credentials", mount_path=ssh_mount_path),
            ])
            init_cmd += (
                f" && cp /ssh-secret/id_rsa.agent {ssh_mount_path}/id_rsa.agent"
                f" && cp /ssh-secret/config {ssh_mount_path}/config"
                f" && chmod 600 {ssh_mount_path}/id_rsa.agent"
            )
            # Pre-populate known_hosts via ssh-keyscan so git clone doesn't
            # need to write to it (and if it does, the mount is writable).
            if ssh_hosts:
                hosts_str = " ".join(ssh_hosts)
                init_cmd += f" && ssh-keyscan {hosts_str} > {ssh_mount_path}/known_hosts 2>/dev/null"
            volume_mounts.append(
                client.V1VolumeMount(name="ssh-credentials", mount_path=ssh_mount_path)
            )
            ssh_cmd = f"ssh -i {ssh_mount_path}/id_rsa.agent"
            if ssh_hosts:
                ssh_cmd += f" -o UserKnownHostsFile={ssh_mount_path}/known_hosts"
            ssh_cmd += " -o StrictHostKeyChecking=accept-new"
            env_list.append(
                client.V1EnvVar(name="GIT_SSH_COMMAND", value=ssh_cmd)
            )

        init_containers = [
            client.V1Container(
                name="setup-workspace",
                image=image,
                command=["sh", "-c", init_cmd],
                volume_mounts=init_volume_mounts,
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
                        init_containers=init_containers,
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
            "secret_name": secret_name,
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

        pod_name = handle.runtime_data.get("pod_name", "")
        namespace = handle.runtime_data["namespace"]

        # Get exit code from pod status.
        # After run() finishes (log stream ends), the K8s API may take a moment
        # to report the container as terminated. Retry briefly to avoid returning
        # exit_code=-1 when the container actually exited with 0.
        exit_code = -1
        for attempt in range(5):
            try:
                pod = self.core_v1.read_namespaced_pod(pod_name, namespace)
                for cs in (pod.status.container_statuses or []):
                    if cs.name == "task-runner" and cs.state and cs.state.terminated:
                        exit_code = cs.state.terminated.exit_code
                        break
            except ApiException:
                logger.warning("Failed to read pod status for %s", pod_name, exc_info=True)

            if exit_code != -1:
                break
            if attempt < 4:
                time.sleep(1)

        if exit_code == -1:
            logger.warning("Could not determine exit code for pod %s after retries", pod_name)

        # Get full logs (combined stdout+stderr from the pod)
        full_logs = ""
        try:
            full_logs = self.core_v1.read_namespaced_pod_log(pod_name, namespace)
        except ApiException:
            logger.warning("Failed to read logs from pod %s", pod_name, exc_info=True)

        # Extract structured output from pod logs.
        # The task-runner prints the JSON as the last stdout line; in K8s logs
        # stdout and stderr are merged but the JSON is recognisable by structure.
        stdout = ""
        if full_logs:
            for line in reversed(full_logs.splitlines()):
                stripped = line.strip()
                if stripped.startswith("{") and stripped.endswith("}"):
                    try:
                        import json
                        obj = json.loads(stripped)
                        if "status" in obj and "result" in obj:
                            stdout = stripped
                            logger.info("Extracted structured output from pod logs")
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

        secret_name = handle.runtime_data.get("secret_name", "")
        if secret_name:
            try:
                self.core_v1.delete_namespaced_secret(secret_name, namespace)
                logger.info("Deleted Secret %s", secret_name)
            except ApiException:
                logger.debug("Failed to delete Secret %s", secret_name, exc_info=True)

    # -- Native async overrides (wrap sync K8s calls in executor) -----------

    async def async_prepare(
        self,
        image: str,
        env: dict[str, str],
        files: dict[str, str],
        output_dir: str | None = None,
        skills_tar: bytes | None = None,
        ssh_private_key: str | None = None,
        ssh_config: str | None = None,
        ssh_hosts: list[str] | None = None,
    ) -> RuntimeHandle:
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            None,
            lambda: self.prepare(
                image, env, files, output_dir, skills_tar,
                ssh_private_key, ssh_config, ssh_hosts,
            ),
        )

    async def _async_wait_for_pod(self, job_name: str) -> str:
        """Async version of _wait_for_pod — polls in executor."""
        loop = asyncio.get_event_loop()
        label_selector = f"job-name={job_name}"
        deadline = time.time() + K8S_POD_START_TIMEOUT

        while time.time() < deadline:
            pods = await loop.run_in_executor(
                None,
                lambda: self.core_v1.list_namespaced_pod(
                    self.namespace, label_selector=label_selector
                ),
            )
            for pod in pods.items:
                phase = pod.status.phase
                if phase in ("Running", "Succeeded", "Failed"):
                    return pod.metadata.name
            await asyncio.sleep(2)

        raise TimeoutError(f"Pod for job {job_name} did not start within {K8S_POD_START_TIMEOUT}s")

    async def async_run(self, handle: RuntimeHandle) -> AsyncIterator[str]:
        """Async generator yielding pod log lines."""
        job_name = handle.runtime_data["job_name"]
        namespace = handle.runtime_data["namespace"]

        pod_name = await self._async_wait_for_pod(job_name)
        handle.runtime_data["pod_name"] = pod_name
        logger.info("Streaming logs from pod %s", pod_name)

        loop = asyncio.get_event_loop()
        queue: asyncio.Queue[str | None] = asyncio.Queue()

        def _stream_logs():
            try:
                log_stream = self.core_v1.read_namespaced_pod_log(
                    pod_name, namespace, follow=True, _preload_content=False,
                )
                buf = ""
                for chunk in log_stream:
                    if isinstance(chunk, bytes):
                        chunk = chunk.decode("utf-8", errors="replace")
                    buf += chunk
                    while "\n" in buf:
                        line, buf = buf.split("\n", 1)
                        if line:
                            loop.call_soon_threadsafe(queue.put_nowait, line)
                if buf.strip():
                    loop.call_soon_threadsafe(queue.put_nowait, buf.strip())
            finally:
                loop.call_soon_threadsafe(queue.put_nowait, None)

        task = loop.run_in_executor(None, _stream_logs)
        try:
            while True:
                item = await queue.get()
                if item is None:
                    break
                yield item
        finally:
            await task

    async def async_result(self, handle: RuntimeHandle) -> tuple[int, str, str]:
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self.result, handle)

    async def async_cleanup(self, handle: RuntimeHandle) -> None:
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, self.cleanup, handle)


def cleanup_orphaned_jobs(runtime: KubernetesRuntime) -> None:
    """Clean up orphaned task-runner Jobs and ConfigMaps on worker startup.

    Cross-references each orphaned Job with the task database:
    - Running tasks: move to scheduled (with backoff) or review (if retries exhausted)
    - Non-running or missing tasks: delete silently
    """
    import asyncio
    from datetime import datetime, timedelta, timezone

    from kubernetes.client.rest import ApiException
    from sqlalchemy import select, update as sa_update
    from sqlalchemy.ext.asyncio import AsyncSession

    from database import async_session
    from events import publish_event
    from models import Task

    MAX_RETRIES = 5
    label_selector = "app.kubernetes.io/managed-by=content-manager-worker"

    try:
        jobs = runtime.batch_v1.list_namespaced_job(
            runtime.namespace, label_selector=label_selector
        )
        for job in jobs.items:
            job_name = job.metadata.name
            task_id = job.metadata.labels.get("content-manager/task-id")

            if task_id:
                # Cross-reference with task database
                try:
                    _recover_orphaned_task(task_id)
                except Exception:
                    logger.warning(
                        "Failed to recover task %s for orphaned Job %s",
                        task_id, job_name, exc_info=True,
                    )

            logger.info("Cleaning up orphaned Job %s (task=%s)", job_name, task_id or "unknown")
            try:
                runtime.batch_v1.delete_namespaced_job(
                    job_name, runtime.namespace, propagation_policy="Foreground"
                )
            except ApiException:
                logger.debug("Failed to delete orphaned Job %s", job_name, exc_info=True)

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

        # Clean up orphaned Secrets (SSH credentials)
        secrets = runtime.core_v1.list_namespaced_secret(
            runtime.namespace, label_selector=label_selector
        )
        for secret in secrets.items:
            name = secret.metadata.name
            logger.info("Cleaning up orphaned Secret %s", name)
            try:
                runtime.core_v1.delete_namespaced_secret(name, runtime.namespace)
            except ApiException:
                logger.debug("Failed to delete orphaned Secret %s", name, exc_info=True)
    except ApiException:
        logger.warning("Failed to list orphaned resources", exc_info=True)


def _recover_orphaned_task(task_id: str) -> None:
    """Cross-reference an orphaned K8s Job with the task DB and recover if running.

    Called from the sync cleanup_orphaned_jobs context, uses a new event loop
    to perform the async DB operation.
    """
    import asyncio
    import uuid as _uuid
    from datetime import datetime, timedelta, timezone

    from sqlalchemy import select, func
    from sqlalchemy.ext.asyncio import AsyncSession
    from sqlalchemy.orm import selectinload

    from database import async_session
    from events import publish_event
    from models import Task

    MAX_RETRIES = 5

    async def _do_recover():
        async with async_session() as session:
            result = await session.execute(
                select(Task).options(selectinload(Task.tags)).where(Task.id == _uuid.UUID(task_id))
            )
            task = result.scalar_one_or_none()

            if task is None:
                logger.warning("Orphaned Job references task %s which does not exist in DB", task_id)
                return

            if task.status != "running":
                logger.debug("Orphaned Job task %s has status=%s, no recovery needed", task_id, task.status)
                return

            now = datetime.now(timezone.utc)

            if task.retry_count >= MAX_RETRIES:
                task.status = "review"
                # Get next position
                from sqlalchemy import func as sa_func
                pos_result = await session.execute(
                    select(sa_func.max(Task.position)).where(Task.status == "review")
                )
                task.position = (pos_result.scalar() or 0) + 1
                task.output = (
                    f"Task recovered during worker startup cleanup. "
                    f"Retry count ({task.retry_count}) has reached the maximum ({MAX_RETRIES}). "
                    "Moved to review for manual inspection."
                )
                task.updated_by = "system"
                task.updated_at = now
                task.heartbeat_at = None
                logger.info("Orphaned task %s moved to review (retries exhausted)", task_id)
            else:
                backoff_minutes = 2 ** task.retry_count
                task.status = "scheduled"
                pos_result = await session.execute(
                    select(func.max(Task.position)).where(Task.status == "scheduled")
                )
                task.position = (pos_result.scalar() or 0) + 1
                task.retry_count += 1
                task.execute_at = now + timedelta(minutes=backoff_minutes)
                task.updated_by = "system"
                task.updated_at = now
                task.heartbeat_at = None
                logger.info(
                    "Orphaned task %s recovered to scheduled (retry %d, backoff %dm)",
                    task_id, task.retry_count, backoff_minutes,
                )

            await session.commit()
            await session.refresh(task, ["tags"])

            # Publish WebSocket event
            from scheduler import _task_to_dict
            await publish_event("task_updated", _task_to_dict(task))

    asyncio.run(_do_recover())


# ---------------------------------------------------------------------------
# AppleContainerRuntime
# ---------------------------------------------------------------------------


class AppleContainerRuntime(ContainerRuntime):
    """Runs task-runner containers via the macOS desktop app bridge API."""

    def __init__(self, bridge_url: str, bridge_token: str) -> None:
        self.bridge_url = bridge_url.rstrip("/")
        self.bridge_token = bridge_token
        self._session = requests.Session()
        self._session.headers["Authorization"] = f"Bearer {bridge_token}"

    def prepare(
        self,
        image: str,
        env: dict[str, str],
        files: dict[str, str],
        output_dir: str | None = None,
        skills_tar: bytes | None = None,
        ssh_private_key: str | None = None,
        ssh_config: str | None = None,
        ssh_hosts: list[str] | None = None,
    ) -> RuntimeHandle:
        payload: dict[str, Any] = {
            "image": image,
            "env": env,
            "files": files,
        }
        if skills_tar:
            payload["skills_tar_b64"] = base64.b64encode(skills_tar).decode("ascii")
        if ssh_private_key:
            payload["ssh_private_key"] = ssh_private_key
        if ssh_config:
            payload["ssh_config"] = ssh_config
        if ssh_hosts:
            payload["ssh_hosts"] = ssh_hosts

        resp = self._session.post(f"{self.bridge_url}/containers", json=payload)
        resp.raise_for_status()
        container_id = resp.json()["id"]
        logger.info("Created container %s via bridge API", container_id)

        return RuntimeHandle(runtime_data={"container_id": container_id})

    def run(self, handle: RuntimeHandle) -> Iterator[str]:
        container_id = handle.runtime_data["container_id"]
        resp = self._session.get(
            f"{self.bridge_url}/containers/{container_id}/logs",
            stream=True,
        )
        resp.raise_for_status()

        for raw_line in resp.iter_lines(decode_unicode=True):
            if raw_line and raw_line.startswith("data:"):
                line = raw_line[len("data:"):].strip()
                if line:
                    yield line

    def result(self, handle: RuntimeHandle) -> tuple[int, str, str]:
        container_id = handle.runtime_data["container_id"]

        status_resp = self._session.get(
            f"{self.bridge_url}/containers/{container_id}/status",
        )
        status_resp.raise_for_status()
        status_data = status_resp.json()
        exit_code = status_data.get("exitCode", -1)
        if exit_code is None:
            exit_code = -1
        stderr = status_data.get("logs", "")

        output_resp = self._session.get(
            f"{self.bridge_url}/containers/{container_id}/output",
        )
        output_resp.raise_for_status()
        stdout = output_resp.json().get("output", "")

        return exit_code, stdout, stderr

    def cleanup(self, handle: RuntimeHandle) -> None:
        container_id = handle.runtime_data.get("container_id")
        if container_id:
            try:
                self._session.delete(
                    f"{self.bridge_url}/containers/{container_id}",
                )
                logger.info("Removed container %s via bridge API", container_id)
            except Exception:
                logger.debug("Failed to remove container via bridge API", exc_info=True)


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

    elif runtime_type == "apple":
        bridge_url = os.environ.get("CONTAINER_BRIDGE_URL", "http://localhost:9876")
        bridge_token = os.environ.get("CONTAINER_BRIDGE_TOKEN", "")
        if not bridge_token:
            raise ValueError("CONTAINER_BRIDGE_TOKEN must be set when using apple runtime")
        return AppleContainerRuntime(bridge_url, bridge_token)

    else:
        raise ValueError(f"Unknown CONTAINER_RUNTIME: {runtime_type!r} (expected 'docker', 'kubernetes', or 'apple')")
