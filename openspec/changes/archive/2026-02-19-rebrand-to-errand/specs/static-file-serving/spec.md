## MODIFIED Requirements

### Requirement: Application branding
The HTML page title SHALL be "Errand" (changed from "Content Manager"). The header text SHALL display "Errand". The logo image (`/logo.png`) SHALL use the Errand brand logo.

#### Scenario: Page title
- **WHEN** the app is loaded in a browser
- **THEN** the page title (document.title / `<title>` tag) is "Errand"

#### Scenario: Header branding
- **WHEN** the app renders the header
- **THEN** it displays the text "Errand" and the Errand logo
