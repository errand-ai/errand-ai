"""Unit tests for xml_tool_call_recovery.parse_xml_tool_calls."""

from __future__ import annotations

import json

from xml_tool_call_recovery import parse_xml_tool_calls


def test_attribute_form_function_and_key_value_parameters():
    block = (
        "thinking...\n"
        "<tool_call>"
        "<function=ls>"
        "<parameter=path>/tmp</parameter>"
        "<parameter=long>true</parameter>"
        "</function>"
        "</tool_call>"
    )
    calls, total, sample = parse_xml_tool_calls(block)

    assert total == 1
    assert sample is None
    assert len(calls) == 1
    c = calls[0]
    assert c["type"] == "function"
    assert c["id"].startswith("call_recovered_")
    assert len(c["id"]) == len("call_recovered_") + 12
    assert c["function"]["name"] == "ls"
    assert json.loads(c["function"]["arguments"]) == {"path": "/tmp", "long": "true"}


def test_element_form_function_with_json_arguments():
    block = (
        "<tool_call>"
        "<function_name>fetch</function_name>"
        '<arguments>{"url": "https://example.com", "timeout": 30}</arguments>'
        "</tool_call>"
    )
    calls, total, sample = parse_xml_tool_calls(block)

    assert total == 1
    assert sample is None
    assert len(calls) == 1
    assert calls[0]["function"]["name"] == "fetch"
    assert json.loads(calls[0]["function"]["arguments"]) == {
        "url": "https://example.com",
        "timeout": 30,
    }


def test_verbose_parameter_form():
    block = (
        "<tool_call>"
        "<function=run>"
        "<parameter><name>cmd</name><value>echo hi</value></parameter>"
        "<parameter><name>timeout</name><value>5</value></parameter>"
        "</function>"
        "</tool_call>"
    )
    calls, total, sample = parse_xml_tool_calls(block)

    assert total == 1
    assert sample is None
    assert calls[0]["function"]["name"] == "run"
    assert json.loads(calls[0]["function"]["arguments"]) == {"cmd": "echo hi", "timeout": "5"}


def test_multiple_tool_calls_in_one_reasoning_block():
    reasoning = (
        "first I'll list\n"
        "<tool_call><function=ls><parameter=path>/a</parameter></function></tool_call>\n"
        "then cat\n"
        "<tool_call><function=cat><parameter=path>/a/b</parameter></function></tool_call>"
    )
    calls, total, sample = parse_xml_tool_calls(reasoning)

    assert total == 2
    assert sample is None
    assert [c["function"]["name"] for c in calls] == ["ls", "cat"]
    assert json.loads(calls[0]["function"]["arguments"]) == {"path": "/a"}
    assert json.loads(calls[1]["function"]["arguments"]) == {"path": "/a/b"}
    # Ids are distinct
    assert calls[0]["id"] != calls[1]["id"]


def test_malformed_block_is_skipped_and_sample_returned():
    reasoning = (
        "<tool_call>not a real call, no function tag here</tool_call>\n"
        "<tool_call><function=good><parameter=x>1</parameter></function></tool_call>"
    )
    calls, total, sample = parse_xml_tool_calls(reasoning)

    assert total == 2
    assert len(calls) == 1
    assert calls[0]["function"]["name"] == "good"
    assert sample is not None
    assert "not a real call" in sample


def test_no_tool_call_markup_returns_empty_list():
    calls, total, sample = parse_xml_tool_calls("just some prose, no markup at all")
    assert calls == []
    assert total == 0
    assert sample is None


def test_nested_json_arguments_are_not_truncated():
    """Non-greedy regex would have truncated nested JSON at the first `}`.
    Greedy + </arguments> anchor must capture the full object."""
    block = (
        "<tool_call>"
        "<function_name>configure</function_name>"
        '<arguments>{"server": {"host": "localhost", "port": 8080}, "retries": 3}</arguments>'
        "</tool_call>"
    )
    calls, total, sample = parse_xml_tool_calls(block)

    assert total == 1
    assert sample is None
    assert calls[0]["function"]["name"] == "configure"
    assert json.loads(calls[0]["function"]["arguments"]) == {
        "server": {"host": "localhost", "port": 8080},
        "retries": 3,
    }


def test_failure_sample_is_truncated_to_256_chars():
    big = "x" * 500
    reasoning = f"<tool_call>{big}</tool_call>"
    _, total, sample = parse_xml_tool_calls(reasoning)
    assert total == 1
    assert sample is not None
    assert len(sample) == 256
