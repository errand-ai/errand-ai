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
