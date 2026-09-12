"""Regenerate the cross-repo seam fixture by driving the FastAPI app.

Not collected by a normal run — pytest's `python_files` matches `test_*.py`,
and this is not one. Run it explicitly when a captured shape changes:

    DATABASE_URL="sqlite+aiosqlite:///:memory:" .venv/bin/python -m pytest \
        tests/capture_seam_fixture.py -q -s

The preceding change left no generator behind, so the fixture could only be
reproduced by reconstructing how it had been made. This exists so the next
person does not have to.

Captures verbatim what this repo's endpoints emit, as the original fixture was.
"""
import json
import os
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from local_ai_detection import (
    ENDPOINT_ANSWERED,
    ENDPOINT_NO_ANSWER,
    ENDPOINT_UNAUTHORIZED,
)

OUT = Path(__file__).resolve().parents[2] / "frontend/src/components/__tests__/fixtures/provider-api-capture.json"

OLLAMA = {"object": "list", "data": [{"id": "qwen3:8b", "owned_by": "library"}]}
# Measured from the real LM Studio and oMLX servers on the verification machine.
LM_STUDIO = {"object": "list", "data": [{"id": "qwen/qwen3.8-27b", "owned_by": "organization_owner"}]}

GATEWAY = "host.docker.internal"
LM_URL = f"http://{GATEWAY}:1234/v1"
OMLX_URL = f"http://{GATEWAY}:8000/v1"


def _probes(keyless: dict[int, dict], keyed: dict[int, tuple[dict, str]]):
    """Ollama answers unauthenticated; 1234 and 8000 demand a key."""
    def port(url):
        return int(url.split(":")[2].split("/")[0])

    async def probe_endpoint(base_url, api_key):
        p = port(base_url)
        if p in keyless:
            return ENDPOINT_ANSWERED, keyless[p]
        if p in keyed:
            payload, key = keyed[p]
            return (ENDPOINT_ANSWERED, payload) if api_key == key else (ENDPOINT_UNAUTHORIZED, None)
        return ENDPOINT_NO_ANSWER, None

    async def probe_type(base_url, api_key):
        status, _ = await probe_endpoint(base_url, api_key)
        return "openai_compatible" if status == ENDPOINT_ANSWERED else "unknown"

    return probe_endpoint, probe_type


@pytest.mark.asyncio
async def test_capture(admin_client, monkeypatch):
    monkeypatch.setenv("CREDENTIAL_ENCRYPTION_KEY", "_26HOOIDUcxDH7fkoqI39DZulVPVK-hZe5THhiVLxIs=")
    monkeypatch.setenv("HOST_GATEWAY_ADDRESS", GATEWAY)
    monkeypatch.delenv("CONTAINER_RUNTIME", raising=False)

    keyless = {11434: OLLAMA}
    keyed = {1234: (LM_STUDIO, "sk-lm-studio-key"), 8000: (None, "sk-omlx-key")}
    probe_endpoint, probe_type = _probes(keyless, keyed)

    out = json.loads(OUT.read_text())

    with patch("local_ai_detection.probe_local_endpoint", side_effect=probe_endpoint), \
            patch("local_ai_detection.probe_provider_type", side_effect=probe_type):
        # One keyless runtime registered, two keyed runtimes offered for adoption.
        out["scan_found"] = (await admin_client.post("/api/llm/providers/scan-local")).json()

        async def adopt(url, key, name=None):
            body = {"base_url": url, "api_key": key}
            if name:
                body["name"] = name
            return (await admin_client.post("/api/llm/providers/adopt-local", json=body)).json()

        out["adopt_key_rejected"] = await adopt(LM_URL, "sk-wrong")
        out["adopt_unreachable"] = await adopt(f"http://{GATEWAY}:4891/v1", "sk-anything")
        out["adopt_success"] = await adopt(LM_URL, "sk-lm-studio-key")
        out["adopt_already_configured"] = await adopt(LM_URL, "sk-lm-studio-key")
        out["scan_after_adoption"] = (await admin_client.post("/api/llm/providers/scan-local")).json()

    # name_conflict: the identified name is held elsewhere while the endpoint is free.
    with patch("main.probe_provider_type", new_callable=AsyncMock, return_value="openai_compatible"):
        await admin_client.post("/api/llm/providers", json={
            "name": "lm-studio-2", "base_url": "https://elsewhere.invalid/v1", "api_key": "sk-x",
        })
    keyed[8000] = (LM_STUDIO, "sk-omlx-key")  # identifies as lm-studio, whose -2 name is taken
    probe_endpoint, probe_type = _probes(keyless, keyed)
    with patch("local_ai_detection.probe_local_endpoint", side_effect=probe_endpoint), \
            patch("local_ai_detection.probe_provider_type", side_effect=probe_type):
        out["adopt_name_conflict"] = await adopt(OMLX_URL, "sk-omlx-key")

    with patch.dict(os.environ, {"CONTAINER_RUNTIME": "kubernetes"}):
        out["scan_unavailable"] = (await admin_client.post("/api/llm/providers/scan-local")).json()

    # `providers`, `reachability_*`, `catalog` and `models*` are untouched by
    # this change, and the reachability fixtures are keyed to a provider id in
    # `providers` — regenerating it would break tests that have nothing to do
    # with keyed runtimes.

    OUT.write_text(json.dumps(out, indent=2, sort_keys=True) + "\n")
    print(f"\nWROTE {OUT}")
    for k in ("scan_found", "scan_unavailable", "scan_after_adoption"):
        print(f"  {k}: {json.dumps(out[k])[:160]}")
    for k in sorted(x for x in out if x.startswith("adopt")):
        v = out[k]
        print(f"  {k}: adopted={v.get('adopted')} reason={v.get('reason')} conflicting_name={v.get('conflicting_name')}")
