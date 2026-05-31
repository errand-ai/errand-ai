"""Parse Qwen-XML tool calls emitted in reasoning_content into OpenAI tool-call dicts.

Some open-weights models (e.g. qwen3.x served via LiteLLM/LMStudio) emit tool calls
as XML inside ``reasoning_content`` rather than the structured ``tool_calls`` field.
This module turns those XML blocks back into the OpenAI wire shape so the
agents-SDK can act on them.
"""

from __future__ import annotations

import json
import re
import secrets

_TOOL_CALL_BLOCK_RE = re.compile(r"<tool_call>(.*?)</tool_call>", re.DOTALL)

_FUNCTION_ATTR_RE = re.compile(r"<function\s*=\s*([A-Za-z_][\w\-.]*)\s*>", re.DOTALL)
_FUNCTION_ELEM_RE = re.compile(r"<function_name>\s*([A-Za-z_][\w\-.]*)\s*</function_name>", re.DOTALL)

_ARGUMENTS_JSON_RE = re.compile(r"<arguments>\s*(\{.*?\})\s*</arguments>", re.DOTALL)
_PARAM_ATTR_RE = re.compile(r"<parameter\s*=\s*([A-Za-z_][\w\-.]*)\s*>(.*?)</parameter>", re.DOTALL)
_PARAM_VERBOSE_RE = re.compile(
    r"<parameter>\s*<name>\s*(.*?)\s*</name>\s*<value>\s*(.*?)\s*</value>\s*</parameter>",
    re.DOTALL,
)

_SAMPLE_MAX_CHARS = 256


def _extract_function_name(block: str) -> str | None:
    m = _FUNCTION_ATTR_RE.search(block)
    if m:
        return m.group(1)
    m = _FUNCTION_ELEM_RE.search(block)
    if m:
        return m.group(1)
    return None


def _extract_arguments(block: str) -> dict | None:
    m = _ARGUMENTS_JSON_RE.search(block)
    if m:
        try:
            parsed = json.loads(m.group(1))
            if isinstance(parsed, dict):
                return parsed
        except json.JSONDecodeError:
            pass

    attr_matches = _PARAM_ATTR_RE.findall(block)
    if attr_matches:
        return {key: value.strip() for key, value in attr_matches}

    verbose_matches = _PARAM_VERBOSE_RE.findall(block)
    if verbose_matches:
        return {key.strip(): value.strip() for key, value in verbose_matches}

    return None


def _new_call_id() -> str:
    return f"call_recovered_{secrets.token_hex(6)}"


def parse_xml_tool_calls(reasoning_content: str) -> tuple[list[dict], int, str | None]:
    """Extract Qwen-XML tool calls from a reasoning_content string.

    Returns ``(recovered_calls, total_blocks_matched, sample_of_first_failure)``.

    ``recovered_calls`` is a list of dicts matching the OpenAI wire shape:
        {"id": str, "type": "function",
         "function": {"name": str, "arguments": json_encoded_str}}

    Malformed individual blocks are skipped; the first failing block (if any)
    is returned as a truncated sample for diagnostics.
    """
    blocks = _TOOL_CALL_BLOCK_RE.findall(reasoning_content)
    total = len(blocks)
    recovered: list[dict] = []
    failure_sample: str | None = None

    for block in blocks:
        name = _extract_function_name(block)
        args = _extract_arguments(block)
        if name is None or args is None:
            if failure_sample is None:
                failure_sample = block.strip()[:_SAMPLE_MAX_CHARS]
            continue
        recovered.append({
            "id": _new_call_id(),
            "type": "function",
            "function": {
                "name": name,
                "arguments": json.dumps(args),
            },
        })

    return recovered, total, failure_sample
