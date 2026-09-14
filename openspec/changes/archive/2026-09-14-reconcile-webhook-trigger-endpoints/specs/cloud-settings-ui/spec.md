## ADDED Requirements

### Requirement: Cloud endpoint display refreshes while the page is open
Because webhook trigger endpoints are now repaired in the background on every cloud reconnect, a trigger's URL can change while the Cloud Service settings page is open. The page SHALL refresh its cloud status and trigger list periodically while mounted, so it does not keep displaying — and offering a Copy button for — a URL that has already been replaced or cleared.

#### Scenario: A repaired URL appears without a reload
- **WHEN** the Cloud Service settings page is open and a reconciliation pass replaces a trigger's `cloud_webhook_url`
- **THEN** the page SHALL show the new URL within one refresh interval
- **AND** SHALL NOT require the user to reload

#### Scenario: A cleared URL stops being offered without a reload
- **WHEN** the page is open and reconciliation clears a trigger's `cloud_webhook_url`
- **THEN** the row SHALL fall back to "Registration failed — re-save trigger to retry"
- **AND** the Copy button SHALL no longer be shown for that row

#### Scenario: The background refresh is not visible as a loading state
- **WHEN** the periodic refresh runs on an already-populated page
- **THEN** the page SHALL NOT display its initial loading skeleton

#### Scenario: The refresh stops when the page is left
- **WHEN** the user navigates away from the Cloud Service settings page
- **THEN** the periodic refresh SHALL stop
