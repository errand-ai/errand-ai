## Purpose

Search and filter controls for the Archived Tasks page — text search, status dropdown, and result count.

## Requirements

### Requirement: Archived tasks search and filter controls
The Archived Tasks page SHALL display a toolbar above the table containing: a text search input that filters tasks by title substring (case-insensitive), a status dropdown filter with options "All", "Archived", and "Deleted", and a result count label showing the number of filtered tasks (e.g. "15 tasks"). The table SHALL display the filtered and sorted subset of tasks using a computed property rather than the raw task list.

#### Scenario: Search filters by title
- **WHEN** the user types "twitter" in the search input
- **THEN** only tasks whose title contains "twitter" (case-insensitive) are shown in the table and the count updates

#### Scenario: Status filter shows only archived
- **WHEN** the user selects "Archived" from the status dropdown
- **THEN** only tasks with status "archived" are shown

#### Scenario: Status filter shows only deleted
- **WHEN** the user selects "Deleted" from the status dropdown
- **THEN** only tasks with status "deleted" are shown

#### Scenario: Combined search and filter
- **WHEN** the user types "quote" in search and selects "Archived" filter
- **THEN** only archived tasks whose title contains "quote" are shown

#### Scenario: Empty search result
- **WHEN** the user types a search term that matches no tasks
- **THEN** the table shows no rows and the count shows "0 tasks"

### Requirement: Archived tasks sortable columns
The Archived Tasks table column headers for Title, Status, and Date SHALL be clickable to toggle sort direction. Clicking a column header SHALL sort the filtered tasks by that column. A visual sort indicator (arrow) SHALL show the current sort column and direction. The default sort SHALL be by Date descending (most recent first).

#### Scenario: Sort by title ascending
- **WHEN** the user clicks the "Title" column header
- **THEN** tasks are sorted alphabetically by title in ascending order and a sort arrow indicates the direction

#### Scenario: Toggle sort direction
- **WHEN** the user clicks the same column header again
- **THEN** the sort direction toggles from ascending to descending (or vice versa)

#### Scenario: Sort by date
- **WHEN** the user clicks the "Date" column header
- **THEN** tasks are sorted by their updated_at timestamp
