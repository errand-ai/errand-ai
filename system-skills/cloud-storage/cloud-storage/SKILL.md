---
name: cloud-storage
description: Use OneDrive cloud storage via the onedrive_* MCP tools — list, read, write, delete, file info, create folder, move. Read this skill before any cloud storage tool call.
---

You have access to OneDrive cloud storage via the `onedrive_*` MCP tools.

## Operations

Available operations: list files, read, write, delete, file info, create folder, move.

Use path-based file access (e.g. `/Documents/report.docx`).

## Concurrency (ETags)

Some operations return an `etag` field. When updating a file, pass the etag you received from the read operation. If the file was modified by another process since you read it, the update will fail with a conflict error — re-read the file and retry.

## Error Handling

- **Permission errors**: The user may not have granted access to the requested file or folder. Report the error clearly.
- **Not found errors**: The file or folder path may be incorrect. Verify the path and try again.
- **Auth errors**: If you receive authentication errors, report that the cloud storage connection may need to be re-established.

## Best Practice

For modifying files: download the file content → modify locally → upload the new version. Avoid attempting in-place edits.
