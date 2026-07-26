"""Tests for transcript parsing, metrics, and infra-vs-judgeable classification."""

import json

import transcript


def _log(*events) -> str:
    # Interleave real event lines with noise (pip output, blank lines) like a
    # real runner_logs blob.
    lines = ["Collecting requests==2.32.3", ""]
    for e in events:
        lines.append(json.dumps(e))
        lines.append("some non-json noise")
    return "\n".join(lines)


def test_parse_skips_noise_and_keeps_events():
    logs = _log({"type": "agent_start", "data": {"agent": "TaskRunner"}},
                {"type": "tool_call", "data": {"tool": "web_search", "args": {"q": "x"}}})
    events = transcript.parse_events(logs)
    assert [e["type"] for e in events] == ["agent_start", "tool_call"]


def test_parse_none_and_empty():
    assert transcript.parse_events(None) == []
    assert transcript.parse_events("") == []


def test_metrics():
    logs = _log(
        {"type": "agent_start", "data": {}},
        {"type": "llm_turn_start", "data": {"model": "m", "turn_id": 1}},
        {"type": "tool_call", "data": {"tool": "web_search", "args": {}}},
        {"type": "tool_call_recovered_from_reasoning", "data": {"function_names": ["web_search"]}},
        {"type": "llm_turn_start", "data": {"model": "m", "turn_id": 2}},
        {"type": "error", "data": {"message": "boom"}},
        {"type": "agent_end", "data": {"output": {"result": "done"}}},
    )
    events = transcript.parse_events(logs)
    assert transcript.extract_metrics(events) == {"turns": 2, "recoveries": 1, "error_events": 1}
    assert transcript.tool_calls(events) == ["web_search"]
    assert transcript.agent_end_output(events) == "done"


def test_attribute_model_from_first_turn():
    logs = _log(
        {"type": "agent_start", "data": {}},
        {"type": "llm_turn_start", "data": {"model": "unknown"}},
        {"type": "llm_turn_start", "data": {"model": "gemma-3-27b"}},
    )
    events = transcript.parse_events(logs)
    assert transcript.attribute_model(events) == "gemma-3-27b"  # skips 'unknown'


def test_attribute_model_none_when_absent():
    logs = _log({"type": "agent_start", "data": {}})
    assert transcript.attribute_model(transcript.parse_events(logs)) is None


def test_classify_no_agent_start_is_infra():
    logs = _log({"type": "error", "data": {"message": "startup died"}})
    assert transcript.classify(transcript.parse_events(logs)) == "infra_failure"


def test_classify_pip_failure_is_infra():
    logs = _log(
        {"type": "agent_start", "data": {}},
        {"type": "error", "data": {"message": "Could not install packages from requirements.txt"}},
    )
    assert transcript.classify(transcript.parse_events(logs)) == "infra_failure"


def test_classify_mcp_connection_failure_is_infra():
    logs = _log(
        {"type": "agent_start", "data": {}},
        {"type": "error", "data": {"message": "Failed to connect to MCP server hindsight"}},
    )
    assert transcript.classify(transcript.parse_events(logs)) == "infra_failure"


def test_classify_completed_but_wrong_is_judgeable():
    # agent_start present, ordinary (non-infra) error, agent_end reached →
    # judgeable model failure, not infra.
    logs = _log(
        {"type": "agent_start", "data": {}},
        {"type": "error", "data": {"message": "the API returned an unexpected value"}},
        {"type": "agent_end", "data": {"output": {"result": "wrong answer"}}},
    )
    assert transcript.classify(transcript.parse_events(logs)) == "judgeable"
