"""Unit tests for container_runtime.py — ContainerRuntime ABC, DockerRuntime, KubernetesRuntime, AppleContainerRuntime."""
from unittest.mock import MagicMock, mock_open, patch

import pytest

from container_runtime import (
    AppleContainerRuntime,
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

        # ConfigMap created with flattened keys
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
    def test_prepare_stores_skills_tar_as_binary_data(self, mock_uuid):
        """prepare() stores skills tar as binaryData in ConfigMap and adds init container."""
        import io as _io
        import tarfile as _tarfile

        runtime = self._make_runtime()

        # Build a small tar archive with a skill file (directory hierarchy)
        buf = _io.BytesIO()
        with _tarfile.open(fileobj=buf, mode="w") as tar:
            data = b"skill content"
            info = _tarfile.TarInfo(name="skills/my-skill/SKILL.md")
            info.size = len(data)
            tar.addfile(info, _io.BytesIO(data))
        skills_bytes = buf.getvalue()

        runtime.prepare(
            image="task-runner:v1",
            env={"_TASK_ID": "42"},
            files={"prompt.txt": "hello"},
            skills_tar=skills_bytes,
        )

        # ConfigMap stores workspace files in data, skills tar in binary_data
        cm_call = runtime.core_v1.create_namespaced_config_map.call_args
        cm = cm_call[0][1]
        assert cm.data == {"prompt.txt": "hello"}
        import base64 as _b64
        assert _b64.b64decode(cm.binary_data["skills.tar"]) == skills_bytes

        # Workspace volume is emptyDir (not ConfigMap)
        job_call = runtime.batch_v1.create_namespaced_job.call_args
        job = job_call[0][1]
        workspace_vol = [v for v in job.spec.template.spec.volumes if v.name == "workspace"][0]
        assert workspace_vol.empty_dir is not None

        # Init container extracts skills tar into workspace
        init_containers = job.spec.template.spec.init_containers
        assert len(init_containers) == 1
        assert init_containers[0].name == "setup-workspace"
        assert "tar xf /config/skills.tar" in init_containers[0].command[2]

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

        # Job mounts SSH credentials at /home/nonroot/.ssh via emptyDir
        job_call = runtime.batch_v1.create_namespaced_job.call_args
        job = job_call[0][1]
        container_spec = job.spec.template.spec.containers[0]
        mount_paths = {vm.mount_path: vm.name for vm in container_spec.volume_mounts}
        assert "/home/nonroot/.ssh" in mount_paths

        # Secret mounted into init container, emptyDir for task-runner container
        vol_names = {v.name: v for v in job.spec.template.spec.volumes}
        assert vol_names["ssh-secret"].secret.secret_name == handle.runtime_data["secret_name"]
        assert vol_names["ssh-credentials"].empty_dir is not None

        # Init container copies key from Secret to emptyDir with correct permissions
        init_container = job.spec.template.spec.init_containers[0]
        init_mounts = {vm.mount_path: vm.name for vm in init_container.volume_mounts}
        assert "/ssh-secret" in init_mounts
        assert "/home/nonroot/.ssh" in init_mounts
        assert "chmod 600" in init_container.command[2]

        # GIT_SSH_COMMAND env var points to the mounted key
        env_dict = {e.name: e.value for e in container_spec.env}
        assert "GIT_SSH_COMMAND" in env_dict
        assert "/home/nonroot/.ssh/id_rsa.agent" in env_dict["GIT_SSH_COMMAND"]

    @patch("uuid.uuid4", return_value=MagicMock(
        __str__=MagicMock(return_value="abcd1234-5678")
    ))
    @patch.dict("os.environ", {}, clear=False)
    def test_prepare_ssh_with_hosts_prepopulates_known_hosts(self, mock_uuid):
        """prepare() runs ssh-keyscan for configured hosts and points GIT_SSH_COMMAND at known_hosts."""
        runtime = self._make_runtime()

        handle = runtime.prepare(
            image="task-runner:v1",
            env={"_TASK_ID": "42"},
            files={"prompt.txt": "hello"},
            ssh_private_key="-----BEGIN RSA PRIVATE KEY-----\nfake\n-----END RSA PRIVATE KEY-----",
            ssh_config="Host github.com\n  IdentityFile ~/.ssh/id_rsa.agent",
            ssh_hosts=["github.com", "gitlab.com"],
        )

        # Init container command includes ssh-keyscan
        job_call = runtime.batch_v1.create_namespaced_job.call_args
        job = job_call[0][1]
        init_container = job.spec.template.spec.init_containers[0]
        init_cmd = init_container.command[2]
        assert "ssh-keyscan github.com gitlab.com" in init_cmd
        assert "known_hosts" in init_cmd

        # Main container mounts ssh-credentials as writable (no read_only)
        container_spec = job.spec.template.spec.containers[0]
        for vm in container_spec.volume_mounts:
            if vm.mount_path == "/home/nonroot/.ssh":
                assert vm.read_only is None or vm.read_only is False
                break
        else:
            raise AssertionError("/home/nonroot/.ssh volume mount not found")

        # GIT_SSH_COMMAND references known_hosts file
        env_dict = {e.name: e.value for e in container_spec.env}
        assert "UserKnownHostsFile" in env_dict["GIT_SSH_COMMAND"]
        assert "/home/nonroot/.ssh/known_hosts" in env_dict["GIT_SSH_COMMAND"]

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
        """result() reads exit code from pod status and extracts output from logs."""
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

        # Pod logs contain structured JSON output as last line
        runtime.core_v1.read_namespaced_pod_log.return_value = (
            "some debug output\n"
            '{"status":"completed","result":"done"}'
        )

        exit_code, stdout, stderr = runtime.result(handle)

        assert exit_code == 0
        assert stdout == '{"status":"completed","result":"done"}'
        assert "some debug output" in stderr

    def test_result_extracts_json_from_mixed_logs(self):
        """result() extracts structured JSON from pod logs with mixed content."""
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
        runtime.core_v1.read_namespaced_pod_log.side_effect = ApiException(status=404)

        with patch("time.sleep"):
            exit_code, stdout, stderr = runtime.result(handle)

        assert exit_code == -1
        assert stdout == ""
        assert stderr == ""

    def test_result_retries_exit_code_detection(self):
        """result() retries when container terminated state is not yet available."""
        runtime = self._make_runtime()
        handle = RuntimeHandle(runtime_data={
            "job_name": "task-runner-abc",
            "pod_name": "pod-abc",
            "namespace": "test-ns",
        })

        # First call: container not yet terminated (state.terminated is None)
        mock_pod_pending = MagicMock()
        cs_pending = MagicMock()
        cs_pending.name = "task-runner"
        cs_pending.state.terminated = None
        mock_pod_pending.status.container_statuses = [cs_pending]

        # Second call: container terminated with exit code 0
        mock_pod_done = MagicMock()
        cs_done = MagicMock()
        cs_done.name = "task-runner"
        cs_done.state.terminated.exit_code = 0
        mock_pod_done.status.container_statuses = [cs_done]

        runtime.core_v1.read_namespaced_pod.side_effect = [mock_pod_pending, mock_pod_done]
        runtime.core_v1.read_namespaced_pod_log.return_value = (
            '{"status":"completed","result":"ok"}'
        )

        with patch("time.sleep"):
            exit_code, stdout, stderr = runtime.result(handle)

        assert exit_code == 0
        assert runtime.core_v1.read_namespaced_pod.call_count == 2

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

    @patch("container_runtime._recover_orphaned_task")
    def test_cleans_up_orphaned_jobs_configmaps_and_secrets(self, mock_recover):
        """cleanup_orphaned_jobs deletes all matching Jobs, ConfigMaps, and Secrets."""
        runtime = self._make_runtime()

        # Mock list responses
        mock_job = MagicMock()
        mock_job.metadata.name = "task-runner-old"
        mock_job.metadata.labels = {"content-manager/task-id": "abc-123"}
        runtime.batch_v1.list_namespaced_job.return_value.items = [mock_job]

        mock_cm = MagicMock()
        mock_cm.metadata.name = "task-runner-old"
        runtime.core_v1.list_namespaced_config_map.return_value.items = [mock_cm]

        mock_secret = MagicMock()
        mock_secret.metadata.name = "task-runner-ssh-old"
        runtime.core_v1.list_namespaced_secret.return_value.items = [mock_secret]

        cleanup_orphaned_jobs(runtime)

        mock_recover.assert_called_once_with("abc-123")
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

    @patch("container_runtime._recover_orphaned_task")
    def test_handles_delete_api_error(self, mock_recover):
        """cleanup_orphaned_jobs continues when individual delete fails."""
        from kubernetes.client.rest import ApiException

        runtime = self._make_runtime()

        mock_job = MagicMock()
        mock_job.metadata.name = "task-runner-fail"
        mock_job.metadata.labels = {"content-manager/task-id": "task-1"}
        runtime.batch_v1.list_namespaced_job.return_value.items = [mock_job]
        runtime.batch_v1.delete_namespaced_job.side_effect = ApiException(status=404)

        runtime.core_v1.list_namespaced_config_map.return_value.items = []
        runtime.core_v1.list_namespaced_secret.return_value.items = []

        # Should not raise
        cleanup_orphaned_jobs(runtime)

    @patch("container_runtime._recover_orphaned_task")
    def test_recovery_failure_does_not_block_cleanup(self, mock_recover):
        """If task recovery fails, the Job is still deleted."""
        runtime = self._make_runtime()
        mock_recover.side_effect = Exception("DB error")

        mock_job = MagicMock()
        mock_job.metadata.name = "task-runner-broken"
        mock_job.metadata.labels = {"content-manager/task-id": "task-broken"}
        runtime.batch_v1.list_namespaced_job.return_value.items = [mock_job]

        runtime.core_v1.list_namespaced_config_map.return_value.items = []
        runtime.core_v1.list_namespaced_secret.return_value.items = []

        # Should not raise — recovery failure is caught
        cleanup_orphaned_jobs(runtime)

        # Job should still be deleted despite recovery failure
        runtime.batch_v1.delete_namespaced_job.assert_called_once()

    @patch("container_runtime._recover_orphaned_task")
    def test_job_without_task_id_label_still_deleted(self, mock_recover):
        """Jobs without the task-id label are deleted without attempting recovery."""
        runtime = self._make_runtime()

        mock_job = MagicMock()
        mock_job.metadata.name = "task-runner-nolabel"
        mock_job.metadata.labels = {}
        runtime.batch_v1.list_namespaced_job.return_value.items = [mock_job]

        runtime.core_v1.list_namespaced_config_map.return_value.items = []
        runtime.core_v1.list_namespaced_secret.return_value.items = []

        cleanup_orphaned_jobs(runtime)

        mock_recover.assert_not_called()
        runtime.batch_v1.delete_namespaced_job.assert_called_once()


# ---------------------------------------------------------------------------
# _recover_orphaned_task (DB integration tests)
# ---------------------------------------------------------------------------

import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

import events as events_module
from container_runtime import _recover_orphaned_task

_TASKS_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS tasks (
    id VARCHAR(36) NOT NULL PRIMARY KEY,
    title TEXT NOT NULL,
    description TEXT,
    status TEXT DEFAULT 'review' NOT NULL,
    category TEXT DEFAULT 'immediate',
    execute_at DATETIME,
    repeat_interval TEXT,
    repeat_until DATETIME,
    position INTEGER DEFAULT 0 NOT NULL,
    output TEXT,
    runner_logs TEXT,
    questions TEXT,
    retry_count INTEGER DEFAULT 0 NOT NULL,
    heartbeat_at DATETIME,
    created_by TEXT,
    updated_by TEXT,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL
)
"""

_TAGS_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS tags (
    id VARCHAR(36) NOT NULL PRIMARY KEY,
    name TEXT NOT NULL UNIQUE
)
"""

_TASK_TAGS_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS task_tags (
    task_id VARCHAR(36) NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
    tag_id VARCHAR(36) NOT NULL REFERENCES tags(id) ON DELETE CASCADE,
    PRIMARY KEY (task_id, tag_id)
)
"""


def _fmt_dt(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%d %H:%M:%S")


async def _insert_task(sf, **overrides) -> str:
    defaults = {
        "id": uuid.uuid4().hex,
        "title": "Test task",
        "status": "running",
        "category": "immediate",
        "position": 0,
        "retry_count": 0,
        "created_at": _fmt_dt(datetime.now(timezone.utc)),
        "updated_at": _fmt_dt(datetime.now(timezone.utc)),
    }
    defaults.update(overrides)
    for key in ("heartbeat_at", "updated_at", "created_at", "execute_at"):
        if key in defaults and isinstance(defaults[key], datetime):
            defaults[key] = _fmt_dt(defaults[key])
    cols = ", ".join(defaults.keys())
    placeholders = ", ".join(f":{k}" for k in defaults.keys())
    async with sf() as session:
        await session.execute(text(f"INSERT INTO tasks ({cols}) VALUES ({placeholders})"), defaults)
        await session.commit()
    return defaults["id"]


async def _get_task(sf, task_id):
    async with sf() as session:
        result = await session.execute(text("SELECT * FROM tasks WHERE id = :id"), {"id": task_id})
        return result.mappings().first()


import asyncio as _asyncio


import tempfile as _tempfile
import os as _os


def _setup_recover_db():
    """Create file-based SQLite DB and return (session_factory, engine, db_path).

    Uses a temp file so asyncio.run() in _recover_orphaned_task (which opens a
    new connection) sees the same data.
    """
    fd, db_path = _tempfile.mkstemp(suffix=".db")
    _os.close(fd)
    engine = create_async_engine(f"sqlite+aiosqlite:///{db_path}", echo=False)

    async def _init():
        async with engine.begin() as conn:
            await conn.execute(text(_TASKS_TABLE_SQL))
            await conn.execute(text(_TAGS_TABLE_SQL))
            await conn.execute(text(_TASK_TAGS_TABLE_SQL))

    _asyncio.run(_init())
    return async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False), engine, db_path


class TestRecoverOrphanedTask:
    """Tests for _recover_orphaned_task DB logic (sync — function uses asyncio.run)."""

    def test_non_running_task_not_modified(self):
        """A task not in running status is left unchanged by orphan recovery."""
        sf, engine, db_path = _setup_recover_db()
        task_id = _asyncio.run(_insert_task(sf, status="completed"))

        with patch("database.async_session", sf), \
             patch("events.publish_event", new_callable=AsyncMock) as mock_pub:
            _recover_orphaned_task(task_id)

        task = _asyncio.run(_get_task(sf, task_id))
        assert task["status"] == "completed"
        mock_pub.assert_not_called()
        _asyncio.run(engine.dispose())
        _os.unlink(db_path)

    def test_missing_task_does_not_raise(self):
        """Recovery for a task ID not in the DB logs a warning and returns."""
        sf, engine, db_path = _setup_recover_db()

        with patch("database.async_session", sf):
            _recover_orphaned_task(str(uuid.uuid4()))

        _asyncio.run(engine.dispose())
        _os.unlink(db_path)

    def test_exhausted_retries_moved_to_review(self):
        """A running task with retry_count >= 5 is moved to review."""
        sf, engine, db_path = _setup_recover_db()
        task_id = _asyncio.run(_insert_task(sf, status="running", retry_count=5))

        with patch("database.async_session", sf), \
             patch("events.publish_event", new_callable=AsyncMock):
            _recover_orphaned_task(task_id)

        task = _asyncio.run(_get_task(sf, task_id))
        assert task["status"] == "review"
        assert "startup cleanup" in task["output"].lower()
        assert task["heartbeat_at"] is None
        _asyncio.run(engine.dispose())
        _os.unlink(db_path)


# ---------------------------------------------------------------------------
# AppleContainerRuntime
# ---------------------------------------------------------------------------


class TestAppleContainerRuntime:
    """Tests for AppleContainerRuntime with mocked bridge API."""

    def _make_runtime(self):
        """Create an AppleContainerRuntime with a mocked requests.Session."""
        with patch("container_runtime.requests") as mock_requests:
            mock_session = MagicMock()
            mock_requests.Session.return_value = mock_session
            runtime = AppleContainerRuntime("http://localhost:9876", "test-token")
        return runtime, mock_session

    def test_prepare_sends_post_to_bridge(self):
        """prepare() POSTs to /containers with correct payload."""
        runtime, session = self._make_runtime()
        session.post.return_value.json.return_value = {"id": "ctr-123"}
        session.post.return_value.raise_for_status = MagicMock()

        handle = runtime.prepare(
            image="task-runner:latest",
            env={"FOO": "bar"},
            files={"input.json": '{"key": "value"}'},
        )

        session.post.assert_called_once_with(
            "http://localhost:9876/containers",
            json={
                "image": "task-runner:latest",
                "env": {"FOO": "bar"},
                "files": {"input.json": '{"key": "value"}'},
            },
        )
        assert isinstance(handle, RuntimeHandle)
        assert handle.runtime_data["container_id"] == "ctr-123"

    def test_prepare_includes_skills_tar(self):
        """prepare() base64-encodes skills_tar and includes it in the payload."""
        import base64

        runtime, session = self._make_runtime()
        session.post.return_value.json.return_value = {"id": "ctr-456"}
        session.post.return_value.raise_for_status = MagicMock()

        skills_data = b"fake-tar-data"
        runtime.prepare(
            image="img:latest",
            env={},
            files={"f.txt": "content"},
            skills_tar=skills_data,
        )

        call_kwargs = session.post.call_args[1]
        payload = call_kwargs["json"]
        assert payload["skills_tar_b64"] == base64.b64encode(skills_data).decode("ascii")

    def test_prepare_includes_ssh_credentials(self):
        """prepare() includes SSH key, config, and hosts in the payload."""
        runtime, session = self._make_runtime()
        session.post.return_value.json.return_value = {"id": "ctr-789"}
        session.post.return_value.raise_for_status = MagicMock()

        runtime.prepare(
            image="img:latest",
            env={},
            files={"f.txt": "content"},
            ssh_private_key="-----BEGIN RSA-----\nfake\n-----END RSA-----",
            ssh_config="Host *\n  StrictHostKeyChecking no",
            ssh_hosts=["github.com"],
        )

        call_kwargs = session.post.call_args[1]
        payload = call_kwargs["json"]
        assert payload["ssh_private_key"] == "-----BEGIN RSA-----\nfake\n-----END RSA-----"
        assert payload["ssh_config"] == "Host *\n  StrictHostKeyChecking no"
        assert payload["ssh_hosts"] == ["github.com"]

    def test_run_streams_sse_logs(self):
        """run() parses SSE data: lines and yields log lines."""
        runtime, session = self._make_runtime()
        handle = RuntimeHandle(runtime_data={"container_id": "ctr-123"})

        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()
        mock_resp.iter_lines.return_value = iter([
            "data: log line 1",
            "data: log line 2",
            "",
            "data: log line 3",
        ])
        session.get.return_value = mock_resp

        lines = list(runtime.run(handle))

        session.get.assert_called_once_with(
            "http://localhost:9876/containers/ctr-123/logs",
            stream=True,
        )
        assert lines == ["log line 1", "log line 2", "log line 3"]

    def test_result_returns_exit_code_and_output(self):
        """result() fetches status and output from bridge API."""
        runtime, session = self._make_runtime()
        handle = RuntimeHandle(runtime_data={"container_id": "ctr-123"})

        status_resp = MagicMock()
        status_resp.json.return_value = {"id": "ctr-123", "status": "exited", "exitCode": 0}
        status_resp.raise_for_status = MagicMock()

        output_resp = MagicMock()
        output_resp.json.return_value = {"output": '{"status":"completed","result":"done"}'}
        output_resp.raise_for_status = MagicMock()

        session.get.side_effect = [status_resp, output_resp]

        exit_code, stdout, stderr = runtime.result(handle)

        assert exit_code == 0
        assert stdout == '{"status":"completed","result":"done"}'
        assert stderr == ""

        # Verify both endpoints were called
        calls = session.get.call_args_list
        assert calls[0][0][0] == "http://localhost:9876/containers/ctr-123/status"
        assert calls[1][0][0] == "http://localhost:9876/containers/ctr-123/output"

    def test_result_handles_null_exit_code(self):
        """result() returns -1 when exitCode is null (container still running)."""
        runtime, session = self._make_runtime()
        handle = RuntimeHandle(runtime_data={"container_id": "ctr-123"})

        status_resp = MagicMock()
        status_resp.json.return_value = {"id": "ctr-123", "status": "running", "exitCode": None}
        status_resp.raise_for_status = MagicMock()

        output_resp = MagicMock()
        output_resp.json.return_value = {"output": ""}
        output_resp.raise_for_status = MagicMock()

        session.get.side_effect = [status_resp, output_resp]

        exit_code, stdout, stderr = runtime.result(handle)

        assert exit_code == -1

    def test_cleanup_sends_delete(self):
        """cleanup() sends DELETE /containers/{id} to bridge API."""
        runtime, session = self._make_runtime()
        handle = RuntimeHandle(runtime_data={"container_id": "ctr-123"})

        runtime.cleanup(handle)

        session.delete.assert_called_once_with(
            "http://localhost:9876/containers/ctr-123",
        )

    def test_cleanup_handles_missing_container_id(self):
        """cleanup() does not raise when container_id is missing."""
        runtime, session = self._make_runtime()
        handle = RuntimeHandle(runtime_data={})

        runtime.cleanup(handle)

        session.delete.assert_not_called()

    def test_cleanup_swallows_exception(self):
        """cleanup() swallows exceptions from the DELETE request."""
        runtime, session = self._make_runtime()
        handle = RuntimeHandle(runtime_data={"container_id": "ctr-123"})
        session.delete.side_effect = Exception("connection refused")

        # Should not raise
        runtime.cleanup(handle)


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

    @patch("container_runtime.requests")
    @patch.dict("os.environ", {"CONTAINER_BRIDGE_TOKEN": "secret-token"})
    def test_create_runtime_apple(self, mock_requests):
        """create_runtime('apple') returns an AppleContainerRuntime."""
        result = create_runtime("apple")

        assert isinstance(result, AppleContainerRuntime)
        assert result.bridge_url == "http://localhost:9876"
        assert result.bridge_token == "secret-token"

    @patch("container_runtime.requests")
    @patch.dict("os.environ", {
        "CONTAINER_BRIDGE_URL": "http://custom:1234",
        "CONTAINER_BRIDGE_TOKEN": "my-token",
    })
    def test_create_runtime_apple_custom_url(self, mock_requests):
        """create_runtime('apple') respects CONTAINER_BRIDGE_URL env var."""
        result = create_runtime("apple")

        assert isinstance(result, AppleContainerRuntime)
        assert result.bridge_url == "http://custom:1234"

    @patch.dict("os.environ", {}, clear=False)
    def test_create_runtime_apple_missing_token_raises(self):
        """create_runtime('apple') raises ValueError when CONTAINER_BRIDGE_TOKEN is not set."""
        import os
        os.environ.pop("CONTAINER_BRIDGE_TOKEN", None)

        with pytest.raises(ValueError, match="CONTAINER_BRIDGE_TOKEN must be set"):
            create_runtime("apple")

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
