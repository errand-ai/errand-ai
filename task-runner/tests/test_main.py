import json
import os
from unittest.mock import patch, MagicMock

from main import write_output_file, post_result_callback


def test_file_output_written_when_dir_exists(tmp_path):
    output = json.dumps({"status": "completed", "result": "done", "questions": []})
    write_output_file(output, output_dir=str(tmp_path))
    result_file = tmp_path / "result.json"
    assert result_file.exists()
    assert result_file.read_text() == output


def test_file_output_skipped_when_dir_missing(tmp_path):
    nonexistent = str(tmp_path / "does_not_exist")
    output = json.dumps({"status": "completed", "result": "done", "questions": []})
    write_output_file(output, output_dir=nonexistent)
    assert not os.path.exists(os.path.join(nonexistent, "result.json"))


def test_file_output_content_matches_stdout(tmp_path, capsys):
    output = json.dumps({"status": "completed", "result": "test result", "questions": []})
    print(output)
    write_output_file(output, output_dir=str(tmp_path))
    captured = capsys.readouterr()
    file_content = (tmp_path / "result.json").read_text()
    assert captured.out.strip() == file_content


def test_file_output_handles_write_failure(tmp_path):
    output = json.dumps({"status": "completed", "result": "done", "questions": []})
    read_only_dir = tmp_path / "readonly"
    read_only_dir.mkdir()
    os.chmod(str(read_only_dir), 0o444)
    try:
        write_output_file(output, output_dir=str(read_only_dir))
    finally:
        os.chmod(str(read_only_dir), 0o755)


def test_file_output_error_scenario(tmp_path):
    """Error output (no structured result) still writes to result.json."""
    # When the agent fails, stdout may be empty and exit code is 1.
    # write_output_file should still write whatever output is provided.
    error_output = ""
    write_output_file(error_output, output_dir=str(tmp_path))
    result_file = tmp_path / "result.json"
    # Empty string is valid — file should exist with empty content
    assert result_file.exists()
    assert result_file.read_text() == ""


def test_file_output_with_error_json(tmp_path):
    """Error JSON from a failed agent run is written correctly."""
    error_output = json.dumps({"status": "error", "result": "Agent failed: API timeout", "questions": []})
    write_output_file(error_output, output_dir=str(tmp_path))
    result_file = tmp_path / "result.json"
    assert result_file.exists()
    data = json.loads(result_file.read_text())
    assert data["status"] == "error"
    assert "API timeout" in data["result"]


# --- Callback POST tests ---


CALLBACK_URL = "http://errand:8000/api/internal/task-result/test-123"
CALLBACK_TOKEN = "abc123"
OUTPUT = '{"status":"completed","result":"done","questions":[]}'


def test_callback_post_success():
    """Successful POST logs success."""
    mock_resp = MagicMock()
    mock_resp.status_code = 200

    with patch.dict(os.environ, {
        "RESULT_CALLBACK_URL": CALLBACK_URL,
        "RESULT_CALLBACK_TOKEN": CALLBACK_TOKEN,
    }), patch("main.httpx.post", return_value=mock_resp) as mock_post:
        post_result_callback(OUTPUT)

    mock_post.assert_called_once_with(
        CALLBACK_URL,
        content=OUTPUT,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {CALLBACK_TOKEN}",
        },
        timeout=10.0,
    )


def test_callback_post_failure_logs_warning():
    """Failed POST logs warning and doesn't raise."""
    mock_resp = MagicMock()
    mock_resp.status_code = 500

    with patch.dict(os.environ, {
        "RESULT_CALLBACK_URL": CALLBACK_URL,
        "RESULT_CALLBACK_TOKEN": CALLBACK_TOKEN,
    }), patch("main.httpx.post", return_value=mock_resp):
        # Should not raise
        post_result_callback(OUTPUT)


def test_callback_post_missing_env_vars_no_op():
    """Missing env vars cause silent no-op."""
    with patch.dict(os.environ, {}, clear=False):
        os.environ.pop("RESULT_CALLBACK_URL", None)
        os.environ.pop("RESULT_CALLBACK_TOKEN", None)
        with patch("main.httpx.post") as mock_post:
            post_result_callback(OUTPUT)
            mock_post.assert_not_called()


def test_callback_post_timeout_handled():
    """Timeout is handled gracefully (no raise)."""
    with patch.dict(os.environ, {
        "RESULT_CALLBACK_URL": CALLBACK_URL,
        "RESULT_CALLBACK_TOKEN": CALLBACK_TOKEN,
    }), patch("main.httpx.post", side_effect=Exception("connection timed out")):
        # Should not raise
        post_result_callback(OUTPUT)
