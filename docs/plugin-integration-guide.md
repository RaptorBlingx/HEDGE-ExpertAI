# Plugin Integration Guide

## Overview

The HEDGE-ExpertAI widget is the production delivery artifact for the project. It is a self-contained JavaScript component with no framework dependency and can be dropped into any page that can load two static files:

- `hedge-expert-widget.js`
- `hedge-expert-widget.css`

Use `server-ip/demo.html` as the smoke-test host page for deployment validation. The React validation console is a development tool and is not the canonical delivery surface.

## Quick Integration

### Option 1: Script tag with auto-initialization

Add this just before `</body>`:

```html
<link rel="stylesheet" href="https://your-host/hedge-expert-widget.css" />
<script
  src="https://your-host/hedge-expert-widget.js"
  data-hedge-expert
  data-api-url="https://your-host"
  data-title="HEDGE-ExpertAI"
  data-subtitle="IoT App Discovery Assistant"
  data-position="bottom-right"
  data-primary-color="#0ea5e9"
  data-width="400px"
  data-height="580px"
></script>
```

### Option 2: Manual initialization

```html
<link rel="stylesheet" href="https://your-host/hedge-expert-widget.css" />
<script src="https://your-host/hedge-expert-widget.js"></script>
<script>
  const widget = new HedgeExpertWidget({
    apiUrl: "https://your-host",
    title: "HEDGE-ExpertAI",
    subtitle: "IoT App Discovery Assistant",
    primaryColor: "#0ea5e9",
    position: "bottom-right",
    width: "400px",
    height: "580px",
  });
</script>
```

## Configuration Options

| Option | Type | Default | Description |
|---|---|---|---|
| `apiUrl` | string | `window.location.origin` | Gateway origin used by the widget |
| `position` | string | `bottom-right` | `bottom-right` or `bottom-left` |
| `title` | string | `HEDGE-ExpertAI` | Header title |
| `subtitle` | string | `IoT App Discovery Assistant` | Header subtitle |
| `primaryColor` | string | `#0ea5e9` | Theme color used for bubble, header, chips, and CTA |
| `width` | string | `400px` | Desktop panel width |
| `height` | string | `580px` | Desktop panel height |
| `cssUrl` | string | widget-relative path | Override stylesheet location if needed |

## Runtime Behavior

- SSE streaming via the gateway, including Thinking and Typing states.
- Side pane with Recommended Context cards.
- Feedback controls for recommended apps.
- Copy-response action for assistant answers.
- Session continuity via `sessionStorage`.
- Full-screen mobile layout below tablet widths.

## API Contract

The widget requires these gateway endpoints:

- `POST /api/v1/chat/stream`
  - Request: `{"session_id": "...", "message": "..."}`
  - Response: server-sent events with token chunks, recommended apps, and session completion metadata.
- `POST /api/v1/feedback`
  - Optional but recommended.
  - Used for `accept` and `dismiss` actions on recommendations.

The widget does not depend on the validation-console catalog endpoints.

## Security Notes

- Serve the widget over HTTPS in production.
- Ensure `CORS_ALLOWED_ORIGINS` allows the embedding host.
- Session IDs are stored in `sessionStorage`, not cookies.
- The widget assumes the gateway handles auth, rate limiting, and headers.

## Styling Hooks

All runtime classes use the `.he-` prefix.

Useful CSS custom properties set on the widget container:

- `--he-primary`
- `--he-primary-dark`
- `--he-primary-soft`
- `--he-panel-width`
- `--he-panel-height`

Example override:

```css
.he-container {
  --he-primary: #f97316;
  --he-primary-dark: #c2410c;
  --he-primary-soft: #fdba74;
}
```

## Deployment Path

Recommended public files:

- `https://server-ip/demo.html` — smoke-test host page
- `https://server-ip/hedge-expert-widget.js` — widget asset
- `https://server-ip/hedge-expert-widget.css` — widget stylesheet

For a step-by-step deployment flow, see [Widget Quick Start](widget-quick-start.md).
