## Context

The Cloud Service settings page has connected, not-connected, and error states. The connected state shows a green indicator, tenant ID, subscription info, and a Disconnect button. There is no link to the cloud account management portal.

## Goals

- Provide a clear path from the settings page to the cloud account portal
- Open in a new tab so the user doesn't lose their settings context

## Non-Goals

- Embedding or proxying the cloud account portal
- Making the URL configurable (it's a fixed public URL)

## Decision 1: Simple anchor-style button

**Approach**: Add a styled link (`<a>` with `target="_blank"`) next to the Disconnect button in the connected state. Use a neutral/secondary button style to distinguish it from the destructive Disconnect button.

**Why not a `<button>` with `window.open`?** A semantic `<a>` tag with `target="_blank"` is more accessible, supports right-click "Open in new tab", and doesn't require JavaScript.
