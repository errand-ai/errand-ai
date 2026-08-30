"""Tests for migration 031's bytes-repr detection.

The detection is the only risky part of the change: it rewrites stored data
one-way. These tests pin the conjunction — a value is repaired only when every
condition holds — and, just as importantly, that anything ambiguous is left
byte-for-byte alone.
"""
import importlib.util
import pathlib

import pytest

_spec = importlib.util.spec_from_file_location(
    "migration_031",
    pathlib.Path(__file__).resolve().parents[1]
    / "alembic" / "versions" / "031_repair_bytes_repr_runner_logs.py",
)
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)
decode = _mod._decode_bytes_repr


class TestRepairsGenuineCorruption:
    def test_repairs_a_real_bytes_repr(self):
        original = (
            '{"type":"agent_start","data":{"turn_id":"t1"}}\n'
            '{"type":"llm_turn_end","data":{"input_tokens":1234}}\n'
            "Collecting google-genai\n"
        )
        corrupt = repr(original.encode("utf-8"))  # exactly what str(bytes) produced

        result = decode(corrupt)

        assert result == original
        assert "\n" in result
        assert not result.startswith("b'")

    def test_repaired_lines_are_independently_parseable(self):
        """The property the log viewer depends on."""
        import json

        original = (
            '{"type":"agent_start","data":{}}\n'
            '{"type":"tool_call","data":{"name":"read_url"}}\n'
        )
        result = decode(repr(original.encode("utf-8")))

        types = [
            json.loads(ln)["type"]
            for ln in result.split("\n")
            if ln.strip()
        ]
        assert types == ["agent_start", "tool_call"]

    def test_repairs_double_quoted_repr(self):
        corrupt = repr(b"it's got an apostrophe\nsecond line\n")
        assert corrupt.startswith('b"')  # Python picks double quotes here
        assert decode(corrupt) == "it's got an apostrophe\nsecond line\n"

    def test_replaces_undecodable_bytes_rather_than_failing(self):
        corrupt = repr(b"valid text \xff\xfe more text\n")
        result = decode(corrupt)
        assert result is not None
        assert "valid text" in result


class TestLeavesEverythingElseAlone:
    def test_healthy_log_with_real_newlines_untouched(self):
        healthy = '{"type":"agent_start","data":{}}\nCollecting pillow\n'
        assert decode(healthy) is None

    def test_healthy_log_that_legitimately_starts_with_b(self):
        """A real log may begin with 'b' — only the full conjunction identifies corruption."""
        healthy = "building wheel for pillow\nb'this is just text'\n"
        assert decode(healthy) is None

    def test_truncated_repr_is_skipped_not_guessed(self):
        """truncate_output bounds by encoded byte length and can cut the closing quote.

        Production currently has none of these, but the migration must not invent a
        repair for a value it cannot parse.
        """
        full = repr(("x" * 500 + "\n").encode("utf-8"))
        truncated = full[:200]  # closing quote gone

        assert not truncated.endswith(("'", '"'))
        assert decode(truncated) is None

    def test_repr_of_a_non_bytes_object_is_skipped(self):
        assert decode("b'unterminated") is None
        assert decode(repr("b'a str, not bytes'")) is None

    @pytest.mark.parametrize("value", ["", "b", "b'", None, 123])
    def test_degenerate_values_are_skipped(self, value):
        assert decode(value) is None

    def test_value_with_carriage_return_is_skipped(self):
        assert decode("b'has\r a real CR'") is None
