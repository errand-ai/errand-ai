# Task Completion Checklist

When a coding task is completed, perform the following:

1. **Local Testing**: Run `docker compose -f testing/docker-compose.yml up` and verify the affected functionality works
2. **Build Check**: Ensure Docker images build without errors (`docker compose -f testing/docker-compose.yml up --build`)
3. **Review Changes**: Check that changes are minimal and focused on the task
4. **No Broken Imports**: Verify no circular imports or missing modules
5. **Update OpenSpec Tasks**: Mark completed tasks in the tasks.md file (`- [ ]` → `- [x]`)

## Notes
- No linting or formatting tools are configured yet (greenfield project)
- No test framework is set up yet
- Always verify locally before committing
