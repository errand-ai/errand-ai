"""Block Kit message builders for Slack responses."""


def status_emoji(status: str) -> str:
    """Map task status to Slack emoji."""
    emojis = {
        "new": ":white_circle:",
        "scheduled": ":clock3:",
        "pending": ":hourglass_flowing_sand:",
        "running": ":gear:",
        "review": ":eyes:",
        "completed": ":white_check_mark:",
        "archived": ":file_cabinet:",
        "deleted": ":wastebasket:",
    }
    return emojis.get(status, ":question:")


def _task_action_buttons(task_id: str) -> dict:
    """Actions block with View Status and View Output buttons."""
    return {
        "type": "actions",
        "elements": [
            {
                "type": "button",
                "text": {"type": "plain_text", "text": "View Status"},
                "action_id": "task_status",
                "value": str(task_id),
            },
            {
                "type": "button",
                "text": {"type": "plain_text", "text": "View Output"},
                "action_id": "task_output",
                "value": str(task_id),
            },
        ],
    }


def task_created_blocks(task) -> dict:
    """Block Kit response for newly created task."""
    return {
        "response_type": "ephemeral",
        "blocks": [
            {"type": "header", "text": {"type": "plain_text", "text": "Task Created"}},
            {
                "type": "section",
                "fields": [
                    {"type": "mrkdwn", "text": f"*Title:*\n{task.title}"},
                    {"type": "mrkdwn", "text": f"*Status:*\n{status_emoji(task.status)} {task.status}"},
                    {"type": "mrkdwn", "text": f"*Category:*\n{task.category or 'N/A'}"},
                    {"type": "mrkdwn", "text": f"*ID:*\n`{str(task.id)[:8]}`"},
                ],
            },
            {
                "type": "context",
                "elements": [{"type": "mrkdwn", "text": f"Created by {task.created_by or 'unknown'}"}],
            },
            _task_action_buttons(task.id),
        ],
    }


def task_updated_blocks(task) -> list:
    """Block Kit blocks for an updated task message (used with chat.update).

    Returns a list of blocks (not a full response dict) since chat.update
    takes blocks directly, not the response_type wrapper.
    """
    return [
        {"type": "header", "text": {"type": "plain_text", "text": "Task Created"}},
        {
            "type": "section",
            "fields": [
                {"type": "mrkdwn", "text": f"*Title:*\n{task.title}"},
                {"type": "mrkdwn", "text": f"*Status:*\n{status_emoji(task.status)} {task.status}"},
                {"type": "mrkdwn", "text": f"*Category:*\n{task.category or 'N/A'}"},
                {"type": "mrkdwn", "text": f"*ID:*\n`{str(task.id)[:8]}`"},
            ],
        },
        {
            "type": "context",
            "elements": [{"type": "mrkdwn", "text": f"Created by {task.created_by or 'unknown'}"}],
        },
        _task_action_buttons(task.id),
    ]


def task_status_blocks(task) -> dict:
    """Block Kit response for task status."""
    blocks = [
        {"type": "header", "text": {"type": "plain_text", "text": task.title[:150]}},
        {
            "type": "section",
            "fields": [
                {"type": "mrkdwn", "text": f"*Status:*\n{status_emoji(task.status)} {task.status}"},
                {"type": "mrkdwn", "text": f"*Category:*\n{task.category or 'N/A'}"},
                {"type": "mrkdwn", "text": f"*ID:*\n`{str(task.id)[:8]}`"},
                {"type": "mrkdwn", "text": f"*Created:*\n{task.created_at}"},
                {"type": "mrkdwn", "text": f"*Updated:*\n{task.updated_at}"},
            ],
        },
    ]
    context_parts = []
    if task.created_by:
        context_parts.append(f"Created by {task.created_by}")
    if task.updated_by:
        context_parts.append(f"Updated by {task.updated_by}")
    if context_parts:
        blocks.append({
            "type": "context",
            "elements": [{"type": "mrkdwn", "text": " | ".join(context_parts)}],
        })
    return {"response_type": "ephemeral", "blocks": blocks}


def task_list_blocks(tasks: list, status_filter: str | None = None) -> dict:
    """Block Kit response for task list."""
    header_text = f"Tasks ({status_filter})" if status_filter else "Tasks"
    blocks = [
        {"type": "header", "text": {"type": "plain_text", "text": header_text}},
    ]
    if not tasks:
        blocks.append({"type": "section", "text": {"type": "mrkdwn", "text": "No tasks found"}})
    else:
        display = tasks[:20]
        # Group by status
        grouped: dict[str, list] = {}
        for t in display:
            grouped.setdefault(t.status, []).append(t)
        for status, group in grouped.items():
            lines = [f"{status_emoji(status)} `{str(t.id)[:8]}` {t.title}" for t in group]
            blocks.append({"type": "section", "text": {"type": "mrkdwn", "text": "\n".join(lines)}})
        if len(tasks) > 20:
            blocks.append({
                "type": "context",
                "elements": [{"type": "mrkdwn", "text": f"...and {len(tasks) - 20} more"}],
            })
    return {"response_type": "ephemeral", "blocks": blocks}


def task_output_blocks(task) -> dict:
    """Block Kit response for task output."""
    blocks = [
        {"type": "header", "text": {"type": "plain_text", "text": f"Output: {task.title}"[:150]}},
    ]
    if not task.output:
        blocks.append({
            "type": "section",
            "text": {"type": "mrkdwn", "text": f"Task is in status '{task.status}' \u2014 no output yet"},
        })
    else:
        output = task.output
        if len(output) > 2900:
            output = output[:2900] + "\n... (truncated \u2014 view full output in web UI)"
        blocks.append({
            "type": "section",
            "text": {"type": "mrkdwn", "text": f"```\n{output}\n```"},
        })
    return {"response_type": "ephemeral", "blocks": blocks}


def error_blocks(message: str) -> dict:
    """Block Kit error response."""
    return {
        "response_type": "ephemeral",
        "blocks": [
            {"type": "section", "text": {"type": "mrkdwn", "text": f":warning: {message}"}},
        ],
    }


def help_blocks() -> dict:
    """Block Kit help response listing available subcommands."""
    return {
        "response_type": "ephemeral",
        "blocks": [
            {"type": "header", "text": {"type": "plain_text", "text": "Task Commands"}},
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": (
                        "\u2022 `/task new <title>` \u2014 Create a new task\n"
                        "\u2022 `/task status <id>` \u2014 View task status\n"
                        "\u2022 `/task list [status]` \u2014 List tasks\n"
                        "\u2022 `/task run <id>` \u2014 Queue a task for execution\n"
                        "\u2022 `/task output <id>` \u2014 View task output\n"
                        "\u2022 `/task help` \u2014 Show this help message"
                    ),
                },
            },
        ],
    }


# --- Task spec drafts (intake clarification) ---

TASK_SPEC_SUBMIT = "task_spec_submit"
TASK_SPEC_RUN = "task_spec_run"
TASK_SPEC_CANCEL = "task_spec_cancel"
TASK_SPEC_ACTIONS = (TASK_SPEC_SUBMIT, TASK_SPEC_RUN, TASK_SPEC_CANCEL)
# Answers are read back from `state.values[<block_id>][TASK_SPEC_ANSWER]`.
TASK_SPEC_QUESTION_BLOCK_PREFIX = "task_spec_q:"
TASK_SPEC_ANSWER = "answer"


def _plain(text: str, limit: int) -> dict:
    return {"type": "plain_text", "text": text[:limit]}


def _button(text: str, action_id: str, draft_id: str, style: str | None = None) -> dict:
    button = {"type": "button", "text": _plain(text, 75), "action_id": action_id, "value": draft_id}
    if style:
        button["style"] = style
    return button


def _question_block(question: dict) -> dict:
    if question.get("kind") == "choice" and question.get("choices"):
        element = {
            "type": "static_select",
            "action_id": TASK_SPEC_ANSWER,
            "placeholder": _plain("Choose one", 150),
            "options": [
                {"text": _plain(choice, 75), "value": choice[:150]}
                for choice in question["choices"][:100]
            ],
        }
    else:
        element = {"type": "plain_text_input", "action_id": TASK_SPEC_ANSWER}
    return {
        "type": "input",
        "block_id": f"{TASK_SPEC_QUESTION_BLOCK_PREFIX}{question['id']}"[:255],
        "optional": True,
        "label": _plain(question["text"], 2000),
        "element": element,
    }


def _when(preview: dict) -> str:
    if preview.get("category") == "immediate":
        return "Now"
    return preview.get("execute_at") or "Not set"


def task_spec_draft_blocks(view: dict) -> list:
    """The draft as it stands: questions to answer, or a preview to run.

    `view` is `clarify.draft_view(...)`. Every state carries a way to run what
    is there and a way to cancel.
    """
    draft_id = view["id"]
    preview = view["spec_preview"]

    if view["status"] == "drafting":
        blocks = [
            {"type": "header", "text": _plain("A few questions first", 150)},
            {
                "type": "section",
                "text": {"type": "mrkdwn", "text": f"Before I set up *{preview['title']}*, I need to check:"[:3000]},
            },
            *[_question_block(q) for q in view["questions"]],
            {
                "type": "actions",
                "elements": [
                    _button("Submit", TASK_SPEC_SUBMIT, draft_id, "primary"),
                    _button("Just run it", TASK_SPEC_RUN, draft_id),
                    _button("Cancel", TASK_SPEC_CANCEL, draft_id, "danger"),
                ],
            },
        ]
        return blocks

    fields = [
        {"type": "mrkdwn", "text": f"*Title:*\n{preview['title']}"[:2000]},
        {"type": "mrkdwn", "text": f"*Category:*\n{preview['category']}"},
        {"type": "mrkdwn", "text": f"*When:*\n{_when(preview)}"[:2000]},
    ]
    if preview.get("repeat_interval"):
        fields.append({"type": "mrkdwn", "text": f"*Repeats:*\n{preview['repeat_interval']}"[:2000]})
    if preview.get("profile"):
        fields.append({"type": "mrkdwn", "text": f"*Profile:*\n{preview['profile']}"[:2000]})

    blocks = [
        {"type": "header", "text": _plain("I'll do this — run it?", 150)},
        {"type": "section", "fields": fields},
        {"type": "section", "text": {"type": "mrkdwn", "text": preview["description"][:3000]}},
    ]
    if view.get("questions_unresolved") and view["questions"]:
        still_open = "\n".join(f"• {q['text']}" for q in view["questions"])
        blocks.append({
            "type": "context",
            "elements": [{"type": "mrkdwn", "text": f"Still open — I'll use my best judgement:\n{still_open}"[:3000]}],
        })
    blocks.append({
        "type": "actions",
        "elements": [
            _button("Run", TASK_SPEC_RUN, draft_id, "primary"),
            _button("Cancel", TASK_SPEC_CANCEL, draft_id, "danger"),
        ],
    })
    return blocks


def task_spec_notice_blocks(message: str) -> list:
    return [{"type": "section", "text": {"type": "mrkdwn", "text": message[:3000]}}]
