"""Unit tests for container_runtime.py — ContainerRuntime ABC, DockerRuntime, KubernetesRuntime."""
from unittest.mock import MagicMock, mock_open, patch

import pytest

from container_runtime import (
    ContainerRuntime,
    DockerRuntime,
    KubernetesRuntime,
    RuntimeHandle,
    cleanup_orphaned_jobs,
    create_runtime,
    _read_namespace,
    K8S_JOB_TTL_SECONDS,
    _put_archive,
)


# ---------------------------------------------------------------------------
# ContainerRuntime ABC
# ---------------------------------------------------------------------------


def test_container_runtime_abc_cannot_instantiate():
    """ContainerRuntime is abstract and cannot be instantiated directly."""
    with pytest.raises(TypeError):
        ContainerRuntime()


# ---------------------------------------------------------------------------
# DockerRuntime
# ---------------------------------------------------------------------------


class TestDockerRuntime:
    """Tests for DockerRuntime with mocked docker client."""

    def _make_runtime(self):
        client = MagicMock()
        return DockerRuntime(client), client

    def test_prepare_creates_container(self):
        """prepare() creates a container with correct image, env, and network_mode."""
        runtime, client = self._make_runtime()
        client.images.get.return_value = MagicMock()  # image exists locally

        handle = runtime.prepare(
            image="task-runner:latest",
            env={"FOO": "bar"},
            files={"input.json": '{"key": "value"}'},
        )

        client.containers.create.assert_called_once_with(
            image="task-runner:latest",
            environment={"FOO": "bar"},
            network_mode="host",
            detach=True,
        )
        assert isinstance(handle, RuntimeHandle)
        assert "container" in handle.runtime_data

    def test_prepare_pulls_missing_image(self):
        """prepare() pulls the image when it's not found locally."""
        from docker.errors import ImageNotFound

        runtime, client = self._make_runtime()
        client.images.get.side_effect = ImageNotFound("not found")

        runtime.prepare(
            image="task-runner:latest",
            env={},
            files={"input.json": "{}"},
        )

        client.images.pull.assert_called_once_with("task-runner:latest")

    def test_prepare_injects_skills_tar(self):
        """prepare() injects skills tar archive when provided."""
        runtime, client = self._make_runtime()
        client.images.get.return_value = MagicMock()
        container = client.containers.create.return_value

        skills_data = b"fake-tar-data"
        runtime.prepare(
            image="img:latest",
            env={},
            files={"f.txt": "content"},
            skills_tar=skills_data,
        )

        # Second put_archive call should be the skills tar
        assert container.put_archive.call_count == 2
        call_args = container.put_archive.call_args_list[1]
        assert call_args[0][0] == "/workspace"

    def test_prepare_injects_ssh_credentials(self):
        """prepare() injects SSH key and config when both are provided."""
        runtime, client = self._make_runtime()
        client.images.get.return_value = MagicMock()
        container = client.containers.create.return_value

        runtime.prepare(
            image="img:latest",
            env={},
            files={"f.txt": "content"},
            ssh_private_key="-----BEGIN RSA-----\nfake\n-----END RSA-----",
            ssh_config="Host *\n  StrictHostKeyChecking no",
        )

        # put_archive called for workspace files + SSH
        assert container.put_archive.call_count == 2

    def test_run_yields_log_lines(self):
        """run() streams container logs and yields individual lines."""
        runtime, client = self._make_runtime()
        container = MagicMock()
        handle = RuntimeHandle(runtime_data={"container": container})

        container.logs.return_value = iter([
            b"line one\n",
            b"line two\nline three\n",
        ])

        lines = list(runtime.run(handle))
        container.start.assert_called_once()
        assert lines == ["line one", "line two", "line three"]

    def test_run_flushes_partial_line(self):
        """run() flushes a partial line (no trailing newline) at the end."""
        runtime, client = self._make_runtime()
        container = MagicMock()
        handle = RuntimeHandle(runtime_data={"container": container})

        container.logs.return_value = iter([b"no newline at end"])

        lines = list(runtime.run(handle))
        assert lines == ["no newline at end"]

    def test_result_returns_exit_code_and_output(self):
        """result() returns exit code, stdout, and stderr from the container."""
        runtime, client = self._make_runtime()
        container = MagicMock()
        handle = RuntimeHandle(runtime_data={"container": container})

        container.wait.return_value = {"StatusCode": 0}
        container.logs.side_effect = [
            b"stdout content",   # first call: stdout=True, stderr=False
            b"stderr content",   # second call: stdout=False, stderr=True
        ]

        exit_code, stdout, stderr = runtime.result(handle)
        assert exit_code == 0
        assert stdout == "stdout content"
        assert stderr == "stderr content"

    def test_result_default_exit_code(self):
        """result() returns -1 when StatusCode is missing from wait result."""
        runtime, client = self._make_runtime()
        container = MagicMock()
        handle = RuntimeHandle(runtime_data={"container": container})

        container.wait.return_value = {}
        container.logs.side_effect = [b"", b""]

        exit_code, _, _ = runtime.result(handle)
        assert exit_code == -1

    def test_cleanup_removes_container(self):
        """cleanup() removes the container with force=True."""
        runtime, client = self._make_runtime()
        container = MagicMock()
        handle = RuntimeHandle(runtime_data={"container": container})

        runtime.cleanup(handle)

        container.remove.assert_called_once_with(force=True)

    def test_cleanup_handles_missing_container(self):
        """cleanup() does not raise when container key is missing."""
        runtime, client = self._make_runtime()
        handle = RuntimeHandle(runtime_data={})

        # Should not raise
        runtime.cleanup(handle)

    def test_cleanup_swallows_remove_exception(self):
        """cleanup() swallows exceptions from container.remove()."""
        runtime, client = self._make_runtime()
        container = MagicMock()
        container.remove.side_effect = Exception("already removed")
        handle = RuntimeHandle(runtime_data={"container": container})

        # Should not raise
        runtime.cleanup(handle)


# ---------------------------------------------------------------------------
# KubernetesRuntime
# ---------------------------------------------------------------------------


class TestKubernetesRuntime:
    """Tests for KubernetesRuntime with mocked K8s clients."""

    def _make_runtime(self):
        """Create a KubernetesRuntime with mocked K8s clients."""
        with patch("container_runtime.KubernetesRuntime.__init__", return_value=None):
            runtime = KubernetesRuntime.__new__(KubernetesRuntime)
        runtime.core_v1 = MagicMock()
        runtime.batch_v1 = MagicMock()
        runtime.namespace = "test-ns"
        runtime.task_runner_image = "task-runner:latest"
        return runtime

    @patch("uuid.uuid4", return_value=MagicMock(
        __str__=MagicMock(return_value="abcd1234-5678")
    ))
    @patch.dict("os.environ", {}, clear=False)
    def test_prepare_creates_configmap_and_job(self, mock_uuid):
        """prepare() creates a ConfigMap and Job with correct labels."""
        runtime = self._make_runtime()

        handle = runtime.prepare(
            image="task-runner:v1",
            env={"MODEL": "gpt-4", "_TASK_ID": "42"},
            files={"prompt.txt": "do stuff"},
        )

        # ConfigMap created
        runtime.core_v1.create_namespaced_config_map.assert_called_once()
        cm_call = runtime.core_v1.create_namespaced_config_map.call_args
        assert cm_call[0][0] == "test-ns"
        cm = cm_call[0][1]
        assert cm.data == {"prompt.txt": "do stuff"}
        assert cm.metadata.labels["app.kubernetes.io/managed-by"] == "content-manager-worker"
        assert cm.metadata.labels["content-manager/task-id"] == "42"

        # Job created
        runtime.batch_v1.create_namespaced_job.assert_called_once()
        job_call = runtime.batch_v1.create_namespaced_job.call_args
        assert job_call[0][0] == "test-ns"
        job = job_call[0][1]
        assert job.metadata.labels["app.kubernetes.io/managed-by"] == "content-manager-worker"
        assert job.metadata.labels["app.kubernetes.io/component"] == "task-runner"
        assert job.metadata.labels["content-manager/task-id"] == "42"

        # Handle contains expected keys
        assert handle.runtime_data["namespace"] == "test-ns"
        assert handle.runtime_data["task_id"] == "42"
        assert "job_name" in handle.runtime_data
        assert "configmap_name" in handle.runtime_data

    @patch("uuid.uuid4", return_value=MagicMock(
        __str__=MagicMock(return_value="abcd1234-5678")
    ))
    @patch.dict("os.environ", {}, clear=False)
    def test_prepare_filters_internal_env_vars(self, mock_uuid):
        """prepare() filters out env vars starting with underscore."""
        runtime = self._make_runtime()

        runtime.prepare(
            image="task-runner:v1",
            env={"MODEL": "gpt-4", "_TASK_ID": "42", "_INTERNAL": "skip"},
            files={},
        )

        job_call = runtime.batch_v1.create_namespaced_job.call_args
        job = job_call[0][1]
        container_spec = job.spec.template.spec.containers[0]
        env_names = [e.name for e in container_spec.env]
        assert "MODEL" in env_names
        assert "_TASK_ID" not in env_names
        assert "_INTERNAL" not in env_names

    @patch("uuid.uuid4", return_value=MagicMock(
        __str__=MagicMock(return_value="abcd1234-5678")
    ))
    @patch.dict("os.environ", {
        "POD_IP": "10.0.0.5",
        "PLAYWRIGHT_PORT": "3000",
        "PLAYWRIGHT_MCP_IMAGE": "playwright:latest",
    })
    def test_prepare_injects_playwright_url(self, mock_uuid):
        """prepare() adds PLAYWRIGHT_URL env var when POD_IP, port, and image are set."""
        runtime = self._make_runtime()

        runtime.prepare(
            image="task-runner:v1",
            env={"MODEL": "gpt-4", "_TASK_ID": "99"},
            files={},
        )

        job_call = runtime.batch_v1.create_namespaced_job.call_args
        job = job_call[0][1]
        container_spec = job.spec.template.spec.containers[0]
        env_dict = {e.name: e.value for e in container_spec.env}
        assert env_dict["PLAYWRIGHT_URL"] == "http://10.0.0.5:3000/mcp"

    @patch("uuid.uuid4", return_value=MagicMock(
        __str__=MagicMock(return_value="abcd1234-5678")
    ))
    @patch.dict("os.environ", {}, clear=False)
    def test_prepare_injects_skills_tar_into_configmap(self, mock_uuid):
        """prepare() extracts skills tar contents into ConfigMap data."""
        import io as _io
        import tarfile as _tarfile

        runtime = self._make_runtime()

        # Build a small tar archive with a skill file
        buf = _io.BytesIO()
        with _tarfile.open(fileobj=buf, mode="w") as tar:
            data = b"skill content"
            info = _tarfile.TarInfo(name="skills/my-skill/SKILL.md")
            info.size = len(data)
            tar.addfile(info, _io.BytesIO(data))
        skills_bytes = buf.getvalue()

        handle = runtime.prepare(
            image="task-runner:v1",
            env={"_TASK_ID": "42"},
            files={"prompt.txt": "hello"},
            skills_tar=skills_bytes,
        )

        # ConfigMap should contain both original file and extracted skill
        cm_call = runtime.core_v1.create_namespaced_config_map.call_args
        cm = cm_call[0][1]
        assert "prompt.txt" in cm.data
        assert "skills/my-skill/SKILL.md" in cm.data
        assert cm.data["skills/my-skill/SKILL.md"] == "skill content"

    @patch("uuid.uuid4", return_value=MagicMock(
        __str__=MagicMock(return_value="abcd1234-5678")
    ))
    @patch.dict("os.environ", {}, clear=False)
    def test_prepare_creates_ssh_secret(self, mock_uuid):
        """prepare() creates a K8s Secret for SSH credentials and mounts it."""
        runtime = self._make_runtime()

        handle = runtime.prepare(
            image="task-runner:v1",
            env={"_TASK_ID": "42"},
            files={"prompt.txt": "hello"},
            ssh_private_key="-----BEGIN RSA PRIVATE KEY-----\nfake\n-----END RSA PRIVATE KEY-----",
            ssh_config="Host github.com\n  IdentityFile ~/.ssh/id_rsa.agent",
        )

        # Secret created
        runtime.core_v1.create_namespaced_secret.assert_called_once()
        secret_call = runtime.core_v1.create_namespaced_secret.call_args
        secret = secret_call[0][1]
        assert "id_rsa.agent" in secret.string_data
        assert "config" in secret.string_data
        assert secret.metadata.labels["app.kubernetes.io/managed-by"] == "content-manager-worker"

        # Secret name stored in handle for cleanup
        assert handle.runtime_data["secret_name"] != ""

        # Job has SSH volume mount at /etc/ssh-credentials (not ~/.ssh — K8s directory perms)
        job_call = runtime.batch_v1.create_namespaced_job.call_args
        job = job_call[0][1]
        container_spec = job.spec.template.spec.containers[0]
        mount_paths = {vm.mount_path: vm.name for vm in container_spec.volume_mounts}
        assert "/etc/ssh-credentials" in mount_paths

        # Volume uses the secret with restrictive file mode
        vol_names = {v.name: v for v in job.spec.template.spec.volumes}
        ssh_vol = vol_names["ssh-credentials"]
        assert ssh_vol.secret.secret_name == handle.runtime_data["secret_name"]
        assert ssh_vol.secret.default_mode == 0o600

        # GIT_SSH_COMMAND env var points to the mounted key
        env_dict = {e.name: e.value for e in container_spec.env}
        assert "GIT_SSH_COMMAND" in env_dict
        assert "/etc/ssh-credentials/id_rsa.agent" in env_dict["GIT_SSH_COMMAND"]

    @patch("uuid.uuid4", return_value=MagicMock(
        __str__=MagicMock(return_value="abcd1234-5678")
    ))
    @patch.dict("os.environ", {}, clear=False)
    def test_prepare_no_ssh_without_credentials(self, mock_uuid):
        """prepare() does not create a Secret when SSH credentials are not provided."""
        runtime = self._make_runtime()

        handle = runtime.prepare(
            image="task-runner:v1",
            env={"_TASK_ID": "42"},
            files={},
        )

        runtime.core_v1.create_namespaced_secret.assert_not_called()
        assert handle.runtime_data["secret_name"] == ""

    def test_run_streams_pod_logs(self):
        """run() waits for the pod, then streams log lines."""
        runtime = self._make_runtime()

        handle = RuntimeHandle(runtime_data={
            "job_name": "task-runner-abc",
            "namespace": "test-ns",
        })

        # Mock _wait_for_pod
        with patch.object(runtime, "_wait_for_pod", return_value="pod-abc"):
            # Mock log stream
            runtime.core_v1.read_namespaced_pod_log.return_value = iter([
                b"log line 1\n",
                b"log line 2\n",
            ])

            lines = list(runtime.run(handle))

        assert lines == ["log line 1", "log line 2"]
        assert handle.runtime_data["pod_name"] == "pod-abc"

    def test_result_reads_exit_code_and_output(self):
        """result() reads exit code from pod status and output from /output/result.json."""
        runtime = self._make_runtime()

        handle = RuntimeHandle(runtime_data={
            "job_name": "task-runner-abc",
            "pod_name": "pod-abc",
            "namespace": "test-ns",
        })

        # Mock pod status with terminated container
        mock_pod = MagicMock()
        cs = MagicMock()
        cs.name = "task-runner"
        cs.state.terminated.exit_code = 0
        mock_pod.status.container_statuses = [cs]
        runtime.core_v1.read_namespaced_pod.return_value = mock_pod

        # Mock exec to read /output/result.json
        with patch("kubernetes.stream.stream", return_value='{"status":"completed","result":"done"}'):
            # Mock full logs as stderr
            runtime.core_v1.read_namespaced_pod_log.return_value = "full log output"

            exit_code, stdout, stderr = runtime.result(handle)

        assert exit_code == 0
        assert stdout == '{"status":"completed","result":"done"}'
        assert stderr == "full log output"

    def test_result_falls_back_to_log_extraction(self):
        """result() extracts structured JSON from pod logs when exec fails."""
        from kubernetes.client.rest import ApiException

        runtime = self._make_runtime()
        handle = RuntimeHandle(runtime_data={
            "job_name": "task-runner-abc",
            "pod_name": "pod-abc",
            "namespace": "test-ns",
        })

        mock_pod = MagicMock()
        cs = MagicMock()
        cs.name = "task-runner"
        cs.state.terminated.exit_code = 0
        mock_pod.status.container_statuses = [cs]
        runtime.core_v1.read_namespaced_pod.return_value = mock_pod

        # Logs contain mixed stderr logging + stdout JSON (last line)
        combined_logs = (
            "2026-01-01 INFO Starting agent\n"
            "2026-01-01 INFO Processing task\n"
            '{"status":"completed","result":"the answer is 42","questions":[]}'
        )
        runtime.core_v1.read_namespaced_pod_log.return_value = combined_logs

        # Exec fails (simulating RBAC 403)
        with patch("kubernetes.stream.stream", side_effect=ApiException(status=403)):
            exit_code, stdout, stderr = runtime.result(handle)

        assert exit_code == 0
        assert '"status":"completed"' in stdout
        assert '"result":"the answer is 42"' in stdout
        assert stderr == combined_logs

    def test_result_handles_api_errors_gracefully(self):
        """result() returns defaults when K8s API calls fail."""
        from kubernetes.client.rest import ApiException

        runtime = self._make_runtime()
        handle = RuntimeHandle(runtime_data={
            "job_name": "task-runner-abc",
            "pod_name": "pod-abc",
            "namespace": "test-ns",
        })

        runtime.core_v1.read_namespaced_pod.side_effect = ApiException(status=404)

        with patch("kubernetes.stream.stream", side_effect=ApiException(status=404)):
            runtime.core_v1.read_namespaced_pod_log.side_effect = ApiException(status=404)
            exit_code, stdout, stderr = runtime.result(handle)

        assert exit_code == -1
        assert stdout == ""
        assert stderr == ""

    def test_cleanup_deletes_job_and_configmap(self):
        """cleanup() deletes both the Job and ConfigMap."""
        runtime = self._make_runtime()

        handle = RuntimeHandle(runtime_data={
            "job_name": "task-runner-abc",
            "configmap_name": "task-runner-abc",
            "namespace": "test-ns",
        })

        runtime.cleanup(handle)

        runtime.batch_v1.delete_namespaced_job.assert_called_once_with(
            "task-runner-abc",
            "test-ns",
            propagation_policy="Foreground",
        )
        runtime.core_v1.delete_namespaced_config_map.assert_called_once_with(
            "task-runner-abc",
            "test-ns",
        )

    def test_cleanup_deletes_secret_when_present(self):
        """cleanup() deletes the SSH Secret when secret_name is in the handle."""
        runtime = self._make_runtime()

        handle = RuntimeHandle(runtime_data={
            "job_name": "task-runner-abc",
            "configmap_name": "task-runner-abc",
            "secret_name": "task-runner-ssh-abc",
            "namespace": "test-ns",
        })

        runtime.cleanup(handle)

        runtime.core_v1.delete_namespaced_secret.assert_called_once_with(
            "task-runner-ssh-abc",
            "test-ns",
        )

    def test_cleanup_handles_api_errors(self):
        """cleanup() swallows ApiException from delete calls."""
        from kubernetes.client.rest import ApiException

        runtime = self._make_runtime()
        handle = RuntimeHandle(runtime_data={
            "job_name": "task-runner-abc",
            "configmap_name": "task-runner-abc",
            "namespace": "test-ns",
        })

        runtime.batch_v1.delete_namespaced_job.side_effect = ApiException(status=404)
        runtime.core_v1.delete_namespaced_config_map.side_effect = ApiException(status=404)

        # Should not raise
        runtime.cleanup(handle)

    @patch("uuid.uuid4", return_value=MagicMock(
        __str__=MagicMock(return_value="abcd1234-5678")
    ))
    @patch.dict("os.environ", {}, clear=False)
    def test_job_has_ttl(self, mock_uuid):
        """Job spec includes ttlSecondsAfterFinished for orphan protection."""
        runtime = self._make_runtime()

        runtime.prepare(
            image="task-runner:v1",
            env={"_TASK_ID": "1"},
            files={},
        )

        job_call = runtime.batch_v1.create_namespaced_job.call_args
        job = job_call[0][1]
        assert job.spec.ttl_seconds_after_finished == K8S_JOB_TTL_SECONDS


# ---------------------------------------------------------------------------
# cleanup_orphaned_jobs
# ---------------------------------------------------------------------------


class TestCleanupOrphanedJobs:
    """Tests for the cleanup_orphaned_jobs function."""

    def _make_runtime(self):
        with patch("container_runtime.KubernetesRuntime.__init__", return_value=None):
            runtime = KubernetesRuntime.__new__(KubernetesRuntime)
        runtime.core_v1 = MagicMock()
        runtime.batch_v1 = MagicMock()
        runtime.namespace = "test-ns"
        return runtime

    def test_cleans_up_orphaned_jobs_configmaps_and_secrets(self):
        """cleanup_orphaned_jobs deletes all matching Jobs, ConfigMaps, and Secrets."""
        runtime = self._make_runtime()

        # Mock list responses
        mock_job = MagicMock()
        mock_job.metadata.name = "task-runner-old"
        runtime.batch_v1.list_namespaced_job.return_value.items = [mock_job]

        mock_cm = MagicMock()
        mock_cm.metadata.name = "task-runner-old"
        runtime.core_v1.list_namespaced_config_map.return_value.items = [mock_cm]

        mock_secret = MagicMock()
        mock_secret.metadata.name = "task-runner-ssh-old"
        runtime.core_v1.list_namespaced_secret.return_value.items = [mock_secret]

        cleanup_orphaned_jobs(runtime)

        runtime.batch_v1.delete_namespaced_job.assert_called_once_with(
            "task-runner-old",
            "test-ns",
            propagation_policy="Foreground",
        )
        runtime.core_v1.delete_namespaced_config_map.assert_called_once_with(
            "task-runner-old",
            "test-ns",
        )
        runtime.core_v1.delete_namespaced_secret.assert_called_once_with(
            "task-runner-ssh-old",
            "test-ns",
        )

    def test_handles_list_api_error(self):
        """cleanup_orphaned_jobs handles ApiException when listing resources."""
        from kubernetes.client.rest import ApiException

        runtime = self._make_runtime()
        runtime.batch_v1.list_namespaced_job.side_effect = ApiException(status=403)

        # Should not raise
        cleanup_orphaned_jobs(runtime)

    def test_handles_delete_api_error(self):
        """cleanup_orphaned_jobs continues when individual delete fails."""
        from kubernetes.client.rest import ApiException

        runtime = self._make_runtime()

        mock_job = MagicMock()
        mock_job.metadata.name = "task-runner-fail"
        runtime.batch_v1.list_namespaced_job.return_value.items = [mock_job]
        runtime.batch_v1.delete_namespaced_job.side_effect = ApiException(status=404)

        runtime.core_v1.list_namespaced_config_map.return_value.items = []

        # Should not raise
        cleanup_orphaned_jobs(runtime)


# ---------------------------------------------------------------------------
# create_runtime factory
# ---------------------------------------------------------------------------


class TestCreateRuntime:
    """Tests for the create_runtime factory function."""

    @patch("docker.DockerClient")
    def test_create_runtime_docker(self, mock_docker_client_cls):
        """create_runtime('docker') returns a DockerRuntime."""
        mock_client = MagicMock()
        mock_docker_client_cls.return_value = mock_client

        result = create_runtime("docker")

        assert isinstance(result, DockerRuntime)
        mock_client.ping.assert_called_once()

    @patch("container_runtime.cleanup_orphaned_jobs")
    @patch("container_runtime.KubernetesRuntime.__init__", return_value=None)
    def test_create_runtime_kubernetes(self, mock_init, mock_cleanup):
        """create_runtime('kubernetes') returns a KubernetesRuntime."""
        result = create_runtime("kubernetes")

        assert isinstance(result, KubernetesRuntime)
        mock_cleanup.assert_called_once()

    def test_create_runtime_invalid_raises(self):
        """create_runtime raises ValueError for unknown runtime types."""
        with pytest.raises(ValueError, match="Unknown CONTAINER_RUNTIME"):
            create_runtime("podman")


# ---------------------------------------------------------------------------
# _put_archive helper
# ---------------------------------------------------------------------------


class TestPutArchive:
    """Tests for the _put_archive helper function."""

    def test_put_archive_creates_tar_and_copies(self):
        """_put_archive creates a tar with the given files and puts it in the container."""
        container = MagicMock()

        _put_archive(container, {"hello.txt": "world", "data.json": '{"k":"v"}'})

        container.put_archive.assert_called_once()
        call_args = container.put_archive.call_args
        assert call_args[0][0] == "/workspace"

    def test_put_archive_custom_dest(self):
        """_put_archive uses the provided destination path."""
        container = MagicMock()

        _put_archive(container, {"f.txt": "data"}, dest="/custom/path")

        call_args = container.put_archive.call_args
        assert call_args[0][0] == "/custom/path"


# ---------------------------------------------------------------------------
# _read_namespace helper
# ---------------------------------------------------------------------------


class TestReadNamespace:
    """Tests for the _read_namespace helper function."""

    @patch.dict("os.environ", {"TASK_RUNNER_NAMESPACE": "my-ns"})
    def test_returns_env_var_when_set(self):
        """_read_namespace returns TASK_RUNNER_NAMESPACE env var when set."""
        assert _read_namespace() == "my-ns"

    @patch.dict("os.environ", {}, clear=False)
    def test_reads_service_account_file(self):
        """_read_namespace reads namespace from service account mount."""
        # Ensure env var is absent
        import os
        os.environ.pop("TASK_RUNNER_NAMESPACE", None)

        m = mock_open(read_data="production\n")
        with patch("builtins.open", m):
            result = _read_namespace()

        assert result == "production"
        m.assert_called_once_with("/var/run/secrets/kubernetes.io/serviceaccount/namespace")

    @patch.dict("os.environ", {}, clear=False)
    def test_returns_default_when_both_absent(self):
        """_read_namespace returns 'default' when env var and file are absent."""
        import os
        os.environ.pop("TASK_RUNNER_NAMESPACE", None)

        with patch("builtins.open", side_effect=OSError("not found")):
            result = _read_namespace()

        assert result == "default"


# ---------------------------------------------------------------------------
# create_runtime factory — env var default
# ---------------------------------------------------------------------------


class TestCreateRuntimeEnvDefault:
    """Tests for create_runtime defaulting via CONTAINER_RUNTIME env var."""

    @patch("docker.DockerClient")
    @patch.dict("os.environ", {}, clear=False)
    def test_defaults_to_docker_when_env_absent(self, mock_docker_client_cls):
        """create_runtime() with no args and no env var defaults to DockerRuntime."""
        import os
        os.environ.pop("CONTAINER_RUNTIME", None)

        mock_client = MagicMock()
        mock_docker_client_cls.return_value = mock_client

        result = create_runtime()

        assert isinstance(result, DockerRuntime)
        mock_client.ping.assert_called_once()

    @patch("container_runtime.cleanup_orphaned_jobs")
    @patch("container_runtime.KubernetesRuntime.__init__", return_value=None)
    @patch.dict("os.environ", {"CONTAINER_RUNTIME": "kubernetes"})
    def test_reads_env_var_for_kubernetes(self, mock_init, mock_cleanup):
        """create_runtime() with no args reads CONTAINER_RUNTIME env var."""
        result = create_runtime()

        assert isinstance(result, KubernetesRuntime)
        mock_cleanup.assert_called_once()
