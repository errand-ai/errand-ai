"""Programmatic corpus assertions, evaluated before the LLM judge.

Each assertion is a single-key mapping ``{<type>: <argument>}``:
  output_contains: <str>   case-insensitive substring of the final output
  output_regex:    <str>   regex searched against the final output
  tool_called:     <str>   tool name that must appear in the transcript's calls

Each evaluates to pass/fail independently. A rep with any failed assertion is a
``fail`` regardless of the judge's score (see scoring.combine_verdict).
"""

from __future__ import annotations

import re


def evaluate_assertions(
    assertions: list[dict],
    final_output: str | None,
    tool_call_names: list[str],
) -> list[dict]:
    """Evaluate each assertion, returning a detail record per assertion.

    Each record: ``{type, argument, passed, detail?}``. An unparseable regex is a
    failed assertion (not a crash) so a bad corpus entry surfaces as a fail.
    """
    output = final_output or ""
    called = set(tool_call_names)
    results: list[dict] = []
    for a in assertions:
        atype = next(iter(a))
        arg = a[atype]
        passed = False
        detail = None
        if atype == "output_contains":
            passed = str(arg).lower() in output.lower()
        elif atype == "output_regex":
            try:
                passed = re.search(str(arg), output) is not None
            except re.error as exc:
                passed = False
                detail = f"invalid regex: {exc}"
        elif atype == "tool_called":
            passed = str(arg) in called
        else:
            detail = f"unknown assertion type '{atype}'"
        record = {"type": atype, "argument": arg, "passed": passed}
        if detail:
            record["detail"] = detail
        results.append(record)
    return results


def all_passed(results: list[dict]) -> bool:
    return all(r["passed"] for r in results)
