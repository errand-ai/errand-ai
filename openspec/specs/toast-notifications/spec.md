## Purpose

Global toast notification system using vue-sonner for transient success and error feedback messages.

## Requirements

### Requirement: Global toast notification system
The application SHALL provide a global toast notification system mounted at the App.vue level using `vue-sonner`. The `<Toaster>` component SHALL be rendered in App.vue. Toast notifications SHALL appear in the top-right corner of the viewport. Success toasts SHALL auto-dismiss after 3 seconds. Error toasts SHALL persist until manually dismissed. All transient feedback messages across the application (settings save confirmations, error messages, copy confirmations) SHALL use the toast system instead of inline success/error text.

#### Scenario: Success toast on settings save
- **WHEN** an admin saves a setting successfully
- **THEN** a success toast appears briefly in the top-right corner and auto-dismisses after 3 seconds

#### Scenario: Error toast on settings save failure
- **WHEN** a settings save request fails
- **THEN** an error toast appears and persists until the user dismisses it

#### Scenario: Toast accessible from any component
- **WHEN** any component in the application needs to show feedback
- **THEN** it can import `toast` from `vue-sonner` and call `toast.success()` or `toast.error()`
