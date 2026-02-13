## 1. Task Runner JSON Extraction

- [x] 1.1 Add `extract_json` function to `task-runner/main.py` that attempts: (1) direct JSON parse, (2) code-fence extraction anywhere in text, (3) first-`{`-to-last-`}` extraction — returning the first valid parse or None
- [x] 1.2 Replace the existing `startswith("```")` stripping logic in `task-runner/main.py` with a call to `extract_json`, keeping the same fallback (wrap raw output as completed) when extraction returns None
- [x] 1.3 Add tests to `task-runner/test_main.py` covering: preamble before JSON code fence, preamble before bare JSON, bare JSON, code fence at start, and unparseable output

## 2. Worker JSON Extraction

- [x] 2.1 Add the same `extract_json` function to `backend/worker.py`
- [x] 2.2 Replace the existing `startswith("```")` stripping logic in `backend/worker.py` with a call to `extract_json`, keeping the same retry fallback when extraction returns None
- [x] 2.3 Add tests to `backend/tests/test_worker.py` covering: preamble before JSON code fence, preamble before bare JSON, and the existing code-fence-at-start and bare JSON cases
