"""Tests for TaskManager's `_resolve_workspace_mounts` — profile + deployment
config → runtime mount spec, across the docker / kubernetes / apple paths, plus
the disabled and requested-but-unconfigured cases.
"""

from task_manager import _resolve_workspace_mounts


def _settings(enabled: bool, subpath=None) -> dict:
    return {
        "_profile_shared_workspace_enabled": enabled,
        "_profile_shared_workspace_subpath": subpath,
    }


def test_profile_disabled_returns_no_mounts(monkeypatch):
    monkeypatch.setenv("WORKSPACE_ENABLED", "true")
    mounts, unconfigured = _resolve_workspace_mounts(_settings(False))
    assert mounts is None
    assert unconfigured is False


def test_enabled_but_deployment_unconfigured(monkeypatch):
    monkeypatch.delenv("WORKSPACE_ENABLED", raising=False)
    mounts, unconfigured = _resolve_workspace_mounts(_settings(True))
    assert mounts is None
    assert unconfigured is True


def test_kubernetes_pvc_mount(monkeypatch):
    monkeypatch.setenv("WORKSPACE_ENABLED", "true")
    monkeypatch.setenv("CONTAINER_RUNTIME", "kubernetes")
    monkeypatch.setenv("WORKSPACE_PVC_CLAIM", "workspace-shared")
    mounts, unconfigured = _resolve_workspace_mounts(_settings(True, subpath="reports/nginx"))
    assert unconfigured is False
    assert len(mounts) == 1
    m = mounts[0]
    assert m.pvc_claim_name == "workspace-shared"
    assert m.subpath == "reports/nginx"
    assert m.container_path == "/shared"
    assert m.host_path is None


def test_kubernetes_without_claim_is_unconfigured(monkeypatch):
    monkeypatch.setenv("WORKSPACE_ENABLED", "true")
    monkeypatch.setenv("CONTAINER_RUNTIME", "kubernetes")
    monkeypatch.delenv("WORKSPACE_PVC_CLAIM", raising=False)
    mounts, unconfigured = _resolve_workspace_mounts(_settings(True))
    assert mounts is None
    assert unconfigured is True


def test_docker_host_path_folds_subpath(monkeypatch):
    monkeypatch.setenv("WORKSPACE_ENABLED", "true")
    monkeypatch.setenv("CONTAINER_RUNTIME", "docker")
    monkeypatch.setenv("WORKSPACE_HOST_PATH", "/data/workspace")
    monkeypatch.delenv("WORKSPACE_VOLUME", raising=False)
    mounts, unconfigured = _resolve_workspace_mounts(_settings(True, subpath="blogs"))
    assert unconfigured is False
    assert mounts[0].host_path == "/data/workspace/blogs"
    assert mounts[0].pvc_claim_name is None


def test_docker_named_volume_without_subpath(monkeypatch):
    monkeypatch.setenv("WORKSPACE_ENABLED", "true")
    monkeypatch.setenv("CONTAINER_RUNTIME", "docker")
    monkeypatch.delenv("WORKSPACE_HOST_PATH", raising=False)
    monkeypatch.setenv("WORKSPACE_VOLUME", "workspace-nfs")
    mounts, unconfigured = _resolve_workspace_mounts(_settings(True, subpath=None))
    assert unconfigured is False
    assert mounts[0].host_path == "workspace-nfs"


def test_docker_named_volume_with_subpath_refused(monkeypatch):
    """A named volume can't scope to a subpath — refuse rather than over-mount."""
    monkeypatch.setenv("WORKSPACE_ENABLED", "true")
    monkeypatch.setenv("CONTAINER_RUNTIME", "docker")
    monkeypatch.delenv("WORKSPACE_HOST_PATH", raising=False)
    monkeypatch.setenv("WORKSPACE_VOLUME", "workspace-nfs")
    mounts, unconfigured = _resolve_workspace_mounts(_settings(True, subpath="reports"))
    assert mounts is None
    assert unconfigured is True


def test_docker_without_source_is_unconfigured(monkeypatch):
    monkeypatch.setenv("WORKSPACE_ENABLED", "true")
    monkeypatch.setenv("CONTAINER_RUNTIME", "docker")
    monkeypatch.delenv("WORKSPACE_HOST_PATH", raising=False)
    monkeypatch.delenv("WORKSPACE_VOLUME", raising=False)
    mounts, unconfigured = _resolve_workspace_mounts(_settings(True))
    assert mounts is None
    assert unconfigured is True


def test_apple_runtime_uses_host_path(monkeypatch):
    monkeypatch.setenv("WORKSPACE_ENABLED", "true")
    monkeypatch.setenv("CONTAINER_RUNTIME", "apple")
    monkeypatch.setenv("WORKSPACE_HOST_PATH", "/Users/x/Drive/Errand")
    monkeypatch.delenv("WORKSPACE_VOLUME", raising=False)
    mounts, unconfigured = _resolve_workspace_mounts(_settings(True, subpath="reports"))
    assert unconfigured is False
    assert mounts[0].host_path == "/Users/x/Drive/Errand/reports"


def test_apple_runtime_rejects_named_volume(monkeypatch):
    """A Docker named volume is not a valid Apple-bridge mount source."""
    monkeypatch.setenv("WORKSPACE_ENABLED", "true")
    monkeypatch.setenv("CONTAINER_RUNTIME", "apple")
    monkeypatch.delenv("WORKSPACE_HOST_PATH", raising=False)
    monkeypatch.setenv("WORKSPACE_VOLUME", "workspace-nfs")
    mounts, unconfigured = _resolve_workspace_mounts(_settings(True))
    assert mounts is None
    assert unconfigured is True
