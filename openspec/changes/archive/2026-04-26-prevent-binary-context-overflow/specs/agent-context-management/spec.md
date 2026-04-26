## ADDED Requirements

### Requirement: Binary file handling directive in system prompt
The system prompt injected by the server SHALL include a directive instructing the agent never to read binary file contents (images, PDFs, archives, etc.) into the conversation. The directive SHALL explain that binary data will exceed the context window and cause task failure, and SHALL direct the agent to use file-path-based tools for uploading/transferring binary files and metadata commands for inspection.

#### Scenario: System prompt includes binary file directive
- **WHEN** the server prepares the system prompt for a task
- **THEN** the system prompt includes a section about binary file handling that warns against reading binary contents and directs the agent to file-path-based alternatives
