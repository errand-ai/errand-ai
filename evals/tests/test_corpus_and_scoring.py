"""Tests for corpus loading/validation, assertions, digest, judge, and scoring."""

import json

import pytest

import assertions as assertions_mod
import corpus as corpus_mod
import digest as digest_mod
import judge as judge_mod
import scoring as scoring_mod


# --- corpus -----------------------------------------------------------------

_VALID = {
    "id": "job-research/001-x",
    "base_profile": "job-research",
    "description": "Find contract roles.",
    "rubric": "Lists real roles with sources.",
    "assertions": [{"tool_called": "web_search"}, {"output_regex": r"\d+ roles"}],
    "reps": 3,
    "timeout_minutes": 20,
}


def _write(tmp_path, workload, name, data):
    d = tmp_path / "corpus" / workload
    d.mkdir(parents=True, exist_ok=True)
    import yaml
    p = d / name
    p.write_text(yaml.safe_dump(data))
    return str(p)


def test_load_valid_corpus_task(tmp_path):
    path = _write(tmp_path, "job-research", "001-x.yaml", _VALID)
    task = corpus_mod.load_task(path)
    assert task.id == "job-research/001-x"
    assert task.workload == "job-research"
    assert task.reps == 3 and task.timeout_minutes == 20
    assert len(task.assertions) == 2


def test_missing_field_rejected_naming_file_and_field(tmp_path):
    bad = dict(_VALID)
    del bad["rubric"]
    path = _write(tmp_path, "job-research", "002-x.yaml", bad)
    with pytest.raises(corpus_mod.CorpusError) as exc:
        corpus_mod.load_task(path)
    assert "rubric" in str(exc.value) and "002-x.yaml" in str(exc.value)


def test_unknown_assertion_type_rejected(tmp_path):
    bad = dict(_VALID, assertions=[{"frobnicate": "x"}])
    path = _write(tmp_path, "job-research", "003-x.yaml", bad)
    with pytest.raises(corpus_mod.CorpusError) as exc:
        corpus_mod.load_task(path)
    assert "frobnicate" in str(exc.value)


def test_load_corpus_sorted_and_filterable(tmp_path):
    _write(tmp_path, "job-research", "002-b.yaml", dict(_VALID, id="job-research/002-b"))
    _write(tmp_path, "job-research", "001-a.yaml", dict(_VALID, id="job-research/001-a"))
    _write(tmp_path, "translation", "001-t.yaml", dict(_VALID, id="translation/001-t", base_profile="translation"))
    corpus_dir = str(tmp_path / "corpus")
    all_ids = [t.id for t in corpus_mod.load_corpus(corpus_dir)]
    assert all_ids == ["job-research/001-a", "job-research/002-b", "translation/001-t"]
    jr_only = [t.id for t in corpus_mod.load_corpus(corpus_dir, workload="job-research")]
    assert jr_only == ["job-research/001-a", "job-research/002-b"]


# --- assertions -------------------------------------------------------------

def test_assertions_contains_regex_tool_called():
    results = assertions_mod.evaluate_assertions(
        [{"output_contains": "JOBS"}, {"output_regex": r"\d+ jobs found"}, {"tool_called": "read_rss_feed"}],
        final_output="Found 12 jobs found in the market",
        tool_call_names=["read_rss_feed", "web_search"],
    )
    assert [r["passed"] for r in results] == [True, True, True]


def test_assertion_regex_fails_reported():
    results = assertions_mod.evaluate_assertions(
        [{"output_regex": r"\d+ jobs found"}], final_output="no numbers here", tool_call_names=[])
    assert results[0]["passed"] is False
    assert assertions_mod.all_passed(results) is False


def test_assertion_tool_not_called_fails():
    results = assertions_mod.evaluate_assertions(
        [{"tool_called": "read_rss_feed"}], final_output="x", tool_call_names=["web_search"])
    assert results[0]["passed"] is False


# --- digest -----------------------------------------------------------------

def test_digest_includes_calls_and_caps():
    events = [{"type": "agent_start", "data": {}}]
    for i in range(200):
        events.append({"type": "llm_turn_start", "data": {"turn_id": i, "model": "m"}})
        events.append({"type": "tool_call", "data": {"tool": f"tool_{i}", "args": {"x": "y" * 50}}})
        events.append({"type": "tool_result", "data": {"result": "z" * 500}})
    d = digest_mod.build_digest(events, max_chars=2000)
    assert len(d) <= 2000 + 120  # cap + the truncation marker line
    assert "tool_0(" in d
    assert "digest truncated" in d


def test_digest_truncates_long_args_and_results():
    events = [
        {"type": "tool_call", "data": {"tool": "web_search", "args": {"q": "a" * 999}}},
        {"type": "tool_result", "data": {"result": "b" * 999}},
    ]
    d = digest_mod.build_digest(events, max_chars=12000)
    assert "web_search(" in d and "…" in d
    assert "a" * 999 not in d  # argument was truncated


# --- judge ------------------------------------------------------------------

def test_judge_parses_strict_json():
    def fake(prompt, model):
        return json.dumps({"pass": True, "score": 7, "reasons": ["good sourcing"]})
    v = judge_mod.judge_rep("claude-opus-4-8", "desc", "rubric", "out", "digest", run_claude=fake)
    assert v["parsed"] and v["pass"] is True and v["score"] == 7.0
    assert v["reasons"] == ["good sourcing"]


def test_judge_retries_once_then_succeeds():
    calls = {"n": 0}
    def fake(prompt, model):
        calls["n"] += 1
        return "garbage" if calls["n"] == 1 else '{"pass": false, "score": 2, "reasons": []}'
    v = judge_mod.judge_rep("m", "d", "r", "o", "dg", run_claude=fake)
    assert calls["n"] == 2 and v["parsed"] and v["pass"] is False and v["score"] == 2.0


def test_judge_null_score_after_two_failures_preserves_raw():
    def fake(prompt, model):
        return "not json at all"
    v = judge_mod.judge_rep("m", "d", "r", "o", "dg", run_claude=fake)
    assert v["parsed"] is False and v["score"] is None
    assert len(v["raw"]) == 2  # both raw responses preserved


def test_judge_extracts_json_from_fenced_response():
    def fake(prompt, model):
        return 'Here is my verdict:\n```json\n{"pass": true, "score": 9, "reasons": ["x"]}\n```\n'
    v = judge_mod.judge_rep("m", "d", "r", "o", "dg", run_claude=fake)
    assert v["parsed"] and v["score"] == 9.0


# --- scoring combine + orchestration ---------------------------------------

def test_combine_failed_assertion_forces_fail():
    a = [{"type": "tool_called", "argument": "x", "passed": False}]
    verdict, score = scoring_mod.combine_verdict(a, {"pass": True, "score": 8.0})
    assert verdict == "fail" and score == 8.0  # judge said pass, assertion overrides


def test_combine_all_pass_uses_judge():
    a = [{"type": "output_contains", "argument": "x", "passed": True}]
    assert scoring_mod.combine_verdict(a, {"pass": True, "score": 8.0}) == ("pass", 8.0)
    assert scoring_mod.combine_verdict(a, {"pass": False, "score": 3.0}) == ("fail", 3.0)


def test_score_rep_end_to_end():
    task = corpus_mod.CorpusTask(
        id="w/001", workload="w", base_profile="bp", description="d", rubric="r",
        assertions=[{"tool_called": "web_search"}], reps=1, timeout_minutes=10, path="x")
    events = [
        {"type": "agent_start", "data": {}},
        {"type": "llm_turn_start", "data": {"model": "m", "turn_id": 1}},
        {"type": "tool_call", "data": {"tool": "web_search", "args": {}}},
        {"type": "agent_end", "data": {"output": {"result": "answer"}}},
    ]
    def fake(prompt, model):
        return json.dumps({"pass": True, "score": 8, "reasons": []})
    res = scoring_mod.score_rep(task, "answer", events, "claude-opus-4-8", run_claude=fake)
    assert res["verdict"] == "pass" and res["score"] == 8.0
    assert res["turns"] == 1
    assert res["judge_output"]["assertions"][0]["passed"] is True


def test_infra_result_skips_judge():
    events = [{"type": "error", "data": {"message": "requirements.txt install failed"}}]
    res = scoring_mod.infra_result(events)
    assert res["verdict"] == "infra_failure" and res["score"] is None
