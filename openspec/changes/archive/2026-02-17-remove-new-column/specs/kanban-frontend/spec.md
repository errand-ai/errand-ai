## MODIFIED Requirements

### Requirement: Kanban column layout

Each Kanban column SHALL have a minimum width of `min-w-[240px]` and use `flex-1` to fill available space. Column headers SHALL display the column label and a task count in a pill badge (`rounded-full bg-white/70 px-1.5 text-xs font-medium`).

The board SHALL display 5 columns in the following order: Review, Scheduled, Pending, Running, Completed. The "New" column SHALL NOT exist.

#### Scenario: Column order

- **WHEN** the Kanban board renders
- **THEN** the columns appear left-to-right as: Review, Scheduled, Pending, Running, Completed

#### Scenario: No New column

- **WHEN** the Kanban board renders
- **THEN** there is no column labelled "New"

#### Scenario: Column count displayed as pill badge

- **WHEN** the Review column contains 3 tasks
- **THEN** the column header shows "REVIEW" followed by a pill badge containing "3"

#### Scenario: Column minimum width

- **WHEN** the browser viewport is narrower than the total of all columns
- **THEN** each column maintains at least 240px width and the board scrolls horizontally

### Requirement: Kanban skeleton loading state

While tasks are loading, the board SHALL display skeleton placeholders that match the column layout: 5 gray rounded column shapes with `animate-pulse`, each containing 2-3 skeleton card shapes.

#### Scenario: Skeleton shown during initial load

- **WHEN** the Kanban board is fetching tasks for the first time
- **THEN** the board displays 5 skeleton columns with pulsing card placeholders

### Requirement: Kanban empty state

When the board has zero tasks across all columns, the board area SHALL display a centered empty state with an icon, "No tasks yet" heading, and "Create your first task using the form above" guidance text. Individual empty columns SHALL NOT display "No tasks" text — an empty column is self-evident.

#### Scenario: Board-level empty state

- **WHEN** all columns have zero tasks
- **THEN** the board displays a centered empty state icon with guidance text instead of the column layout

#### Scenario: Individual empty column

- **WHEN** the Review column has zero tasks but other columns have tasks
- **THEN** the Review column shows no placeholder text

## MODIFIED Requirements

### Requirement: Task cards display summary information

Each task card SHALL display the task title, any associated tags, and a truncated description preview. The description preview SHALL display the first 2 lines of the task's description text using `line-clamp-2`, styled as `text-xs text-gray-500`. If the task has no description, the preview SHALL be omitted.

Cards with `category === 'repeating'` SHALL display a repeat icon (loop/refresh SVG) alongside the repeat interval text between the title and description.

Cards SHALL display the `execute_at` value as a relative time string on all columns where the value is non-null (not only the Scheduled column).

Cards in the Running column SHALL display a pulsing activity indicator: a blue dot with `animate-ping` overlay and "Running..." text, styled as `text-xs text-blue-600`. The card SHALL also have a `border-l-2 border-blue-400` left border accent when in the running state.

Cards in the Review, Completed, or Scheduled columns SHALL display a "View Output" button (eye icon) when the task has a non-null `output` field.

The delete icon on task cards SHALL NOT be displayed when the user has the `viewer` role (checked via `isViewer` from the auth store). The delete icon SHALL also NOT be displayed on task cards in the Running column, regardless of the user's role.

#### Scenario: Editor sees delete button on review task

- **WHEN** an editor views a task card in the Review column
- **THEN** the delete icon is visible on the card

#### Scenario: No delete button on running tasks

- **WHEN** any user views a task card in the Running column
- **THEN** the delete icon is not rendered on the card

#### Scenario: Delete button visible on completed task for editor

- **WHEN** an editor views a task card in the Completed column
- **THEN** the delete icon is visible on the card
