import json
import os

from main import write_output_file


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
