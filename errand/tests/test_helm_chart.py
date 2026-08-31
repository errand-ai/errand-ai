"""Rendered-template assertions for the Helm chart.

`values.yaml` used to default `server.maxConcurrentTasks: 3`, which emitted
`MAX_CONCURRENT_TASKS` on every deployment and — because env beats database in
`resolve_setting_value` — made `max_concurrent_tasks` permanently readonly in
the settings API. Nothing asserted its absence, so the pin survived unnoticed.
These tests render the chart and lock both halves of the contract: no env var
by default, and the operator override still works when set.
"""

import re
import shutil
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
CHART_DIR = REPO_ROOT / "helm" / "errand"

pytestmark = pytest.mark.skipif(
    shutil.which("helm") is None, reason="helm is not installed"
)


def render_server_deployment(*set_values: str) -> str:
    cmd = [
        "helm", "template", "test", str(CHART_DIR),
        "--show-only", "templates/server-deployment.yaml",
    ]
    for value in set_values:
        cmd += ["--set", value]
    result = subprocess.run(cmd, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    return result.stdout


def test_default_render_omits_max_concurrent_tasks():
    """A default install must leave max_concurrent_tasks editable via the API."""
    assert "MAX_CONCURRENT_TASKS" not in render_server_deployment()


def test_explicit_max_concurrent_tasks_is_emitted():
    """The operator override remains available as an escape hatch."""
    rendered = render_server_deployment("server.maxConcurrentTasks=5")
    assert re.search(
        r'- name: MAX_CONCURRENT_TASKS\s+value: "5"', rendered
    ), rendered
