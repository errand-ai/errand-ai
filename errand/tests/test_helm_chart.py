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


def literal_env_names(rendered: str) -> set[str]:
    """Env var names emitted with a literal `value:` in the rendered output.

    That covers both values.yaml defaults and constants hardcoded in the
    template (e.g. CONTAINER_RUNTIME), which is deliberate: either kind pins the
    variable on every deployment, and it is the pin — not its origin — that
    makes a settings key readonly.

    Excludes `valueFrom:` entries (secretKeyRef and friends): those are emitted
    because a secret is wired up, and whether they actually shadow anything
    depends on the referenced secret existing.
    """
    names = set()
    lines = rendered.splitlines()
    for i, line in enumerate(lines):
        match = re.match(r"\s+- name: ([A-Z][A-Z0-9_]*)$", line)
        if match and i + 1 < len(lines) and re.match(r"\s+value:", lines[i + 1]):
            names.add(match.group(1))
    return names


def test_no_registry_backed_env_var_is_defaulted():
    """No registry-backed env var may be pinned by a literal in the chart.

    Such a pin emits the env var on every deployment; env beats database in
    `resolve_setting_value`, so the setting is readonly in the admin API for the
    life of the deployment. That holds whether the literal comes from a
    values.yaml default or straight from the template. This is the general form
    of the max_concurrent_tasks defect — keep it from recurring under a
    different key.
    """
    from settings_registry import SETTINGS_REGISTRY

    emitted = literal_env_names(render_server_deployment())
    shadowed = sorted(
        f"{key} <- {meta['env_var']}"
        for key, meta in SETTINGS_REGISTRY.items()
        if meta.get("env_var") and meta["env_var"] in emitted
    )
    assert not shadowed, (
        "these settings are pinned readonly on every deployment by a literal "
        "env var in the rendered chart (from a values.yaml default or a "
        "hardcoded template value — check both): " + ", ".join(shadowed)
    )
