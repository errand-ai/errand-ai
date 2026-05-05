---
name: binary-files
description: Handling binary files (images, PDFs, archives). Never read binary contents into the conversation — use file-path-based tools or shell utilities like `file`, `ls -la`, or `identify` to inspect them.
---

Never read binary file contents (images, PDFs, archives, etc.) into the conversation. Binary data will exceed the context window and cause task failure.

## Transferring binary files

Use file-path-based tools that accept a file path argument — for example:

- The OneDrive `onedrive_upload_file` tool (when cloud storage is connected)
- The `gws drive` CLI (when Google Workspace is connected)

These tools stream the file by path, so the bytes never enter the conversation.

## Inspecting binary files

Use `execute_command` with shell utilities that report metadata only:

- `file <path>` — identify the format
- `ls -la <path>` — size and permissions
- A short Python snippet via `python -c "..."` for image dimensions, PDF page counts, etc. — only if the relevant library is already installed in the runner

These produce small text outputs that are safe to read. Do not assume tools like `identify` (ImageMagick) are present — check with `which <tool>` first if you want to use a non-standard utility.
