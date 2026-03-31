# Plugin Integration Guide

## Overview

The HEDGE-ExpertAI chat widget is a self-contained JavaScript component that can be embedded in any web page. It requires no build tools and has zero framework dependencies.

## Quick Integration

### Option 1: Script tag with auto-initialization

Add this to your HTML page, just before `</body>`:

```html
<link rel="stylesheet" href="https://your-cdn.com/hedge-expert-widget.css" />
<script
  src="https://your-cdn.com/hedge-expert-widget.js"
  data-hedge-expert
  data-api-url="https://your-api-gateway.com"
></script>
```

### Option 2: Manual initialization

```html
<link rel="stylesheet" href="https://your-cdn.com/hedge-expert-widget.css" />
<script src="https://your-cdn.com/hedge-expert-widget.js"></script>
<script>
  const widget = new HedgeExpertWidget({
    apiUrl: "https://your-api-gateway.com",
    title: "HEDGE-ExpertAI",
    subtitle: "IoT App Discovery Assistant",
    primaryColor: "#2563eb",
    position: "bottom-right",
  });
</script>
```

## Configuration Options

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `apiUrl` | string | `http://localhost:8000` | Gateway API URL |
| `position` | string | `bottom-right` | `bottom-right` or `bottom-left` |
| `title` | string | `HEDGE-ExpertAI` | Chat panel title |
| `subtitle` | string | `IoT App Discovery Assistant` | Chat panel subtitle |
| `primaryColor` | string | `#2563eb` | Theme color (hex) |
| `width` | string | `380px` | Panel width |
| `height` | string | `520px` | Panel height |

## Features

- **Responsive**: Full-screen on mobile (<480px)
- **Dark mode**: Automatically adapts to system preference
- **Session management**: Maintains conversation context across page navigation
- **App cards**: Displays recommended apps with SAREF category badges and relevance scores
- **Loading states**: Animated dots during API calls
- **Error handling**: Graceful fallback messages on network errors

## API Requirements

The widget communicates with the HEDGE-ExpertAI Gateway API:

- `POST /api/v1/chat` — Send chat messages
  - Request: `{"session_id": "...", "message": "..."}`
  - Response: `{"session_id": "...", "message": "...", "intent": "...", "apps": [...]}`

## Security Notes

- The widget respects CORS policies — ensure the Gateway allows your domain
- Session IDs are stored in `sessionStorage` (cleared when browser tab closes)
- No cookies or local storage used
- All communication is via JSON over HTTPS (in production)

## Customization

### CSS Override

All widget classes are prefixed with `.hedge-expert-` for isolation. Override styles in your stylesheet:

```css
.hedge-expert-bubble {
  width: 64px;
  height: 64px;
}

.hedge-expert-badge {
  background: #fef3c7;
  color: #92400e;
}
```
