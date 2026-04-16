"""Tests for platforms.github.prompt — system prompt template rendering."""

from platforms.github.prompt import render_prompt

# Shared test fixtures
ISSUE_NUMBER = 42
ISSUE_TITLE = "Add dark mode support"
REPO_OWNER = "acme"
REPO_NAME = "widgets"
ISSUE_URL = "https://github.com/acme/widgets/issues/42"
ERRAND_TASK_ID = "abc-123-def"


def _render(**overrides):
    """Helper that renders a prompt with defaults, accepting overrides."""
    defaults = dict(
        issue_number=ISSUE_NUMBER,
        issue_title=ISSUE_TITLE,
        repo_owner=REPO_OWNER,
        repo_name=REPO_NAME,
        issue_url=ISSUE_URL,
        issue_labels=[],
        errand_task_id=ERRAND_TASK_ID,
    )
    defaults.update(overrides)
    return render_prompt(**defaults)


class TestRenderPromptSubstitution:
    """All template parameters are substituted correctly."""

    def test_issue_number_appears(self):
        result = _render()
        assert f"#{ISSUE_NUMBER}" in result

    def test_issue_title_appears(self):
        result = _render()
        assert ISSUE_TITLE in result

    def test_repo_owner_and_name_appear(self):
        result = _render()
        assert f"{REPO_OWNER}/{REPO_NAME}" in result

    def test_clone_url(self):
        result = _render()
        assert f"https://github.com/{REPO_OWNER}/{REPO_NAME}.git" in result

    def test_issue_url_in_pr_body(self):
        result = _render()
        assert f"Relates to {ISSUE_URL}" in result

    def test_errand_task_id(self):
        result = _render()
        assert ERRAND_TASK_ID in result


class TestBranchPrefix:
    """Branch prefix is determined by issue labels."""

    def test_bug_label(self):
        result = _render(issue_labels=["bug"])
        assert "bug/<change-name>" in result

    def test_bug_label_case_insensitive(self):
        result = _render(issue_labels=["Bug"])
        assert "bug/<change-name>" in result

    def test_enhancement_label(self):
        result = _render(issue_labels=["enhancement"])
        assert "feature/<change-name>" in result

    def test_enhancement_label_case_insensitive(self):
        result = _render(issue_labels=["Enhancement"])
        assert "feature/<change-name>" in result

    def test_no_matching_label(self):
        result = _render(issue_labels=["documentation", "urgent"])
        assert "patch/<change-name>" in result

    def test_empty_labels(self):
        result = _render(issue_labels=[])
        assert "patch/<change-name>" in result

    def test_bug_takes_precedence_over_enhancement(self):
        """When both bug and enhancement are present, bug wins."""
        result = _render(issue_labels=["bug", "enhancement"])
        assert "bug/<change-name>" in result


class TestTaskPrompt:
    """Optional task_prompt is appended under Additional Instructions."""

    def test_task_prompt_appended(self):
        result = _render(task_prompt="Use TypeScript strict mode.")
        assert "## Additional Instructions" in result
        assert "Use TypeScript strict mode." in result

    def test_no_task_prompt(self):
        result = _render(task_prompt=None)
        assert "## Additional Instructions" not in result

    def test_empty_string_task_prompt(self):
        result = _render(task_prompt="")
        assert "## Additional Instructions" not in result


class TestStructuredJsonOutput:
    """Template includes structured JSON output instructions."""

    def test_completed_json_block(self):
        result = _render()
        assert '"status": "completed"' in result
        assert '"pr_url"' in result

    def test_aborted_json_block(self):
        result = _render()
        assert '"status": "aborted"' in result
        assert '"reason"' in result

    def test_issue_number_in_json_blocks(self):
        result = _render()
        # The rendered template should have the actual issue number in JSON blocks
        assert f'"issue_number": {ISSUE_NUMBER}' in result


class TestPhaseStructure:
    """Template contains all four phases."""

    def test_phase_1(self):
        result = _render()
        assert "Phase 1" in result
        assert "Discovery and validation" in result

    def test_phase_2(self):
        result = _render()
        assert "Phase 2" in result
        assert "Implementation" in result

    def test_phase_3(self):
        result = _render()
        assert "Phase 3" in result
        assert "Verification and testing" in result

    def test_phase_4(self):
        result = _render()
        assert "Phase 4" in result
        assert "Delivery" in result
