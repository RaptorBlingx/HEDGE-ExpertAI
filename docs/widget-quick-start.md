# Widget Quick Start

## Purpose

This is the shortest path to deploying and validating the production HEDGE-ExpertAI widget.

The shipping surface is:

- `/hedge-expert-widget.js`
- `/hedge-expert-widget.css`
- `/demo.html`

The React validation console at `/` is a development tool and can be ignored for production demos.

## Local Run

```bash
cp .env.example .env
make build
make up
make pull-model
make seed
```

Open:

- `http://localhost:8080/demo.html` for the widget demo
- `https://localhost/demo.html` if the `tls` profile is enabled

## Public Smoke Test

After deploying the gateway container, open:

- `https://server-ip/demo.html`

Use that page to validate that the widget assets are live and that streaming works end to end.

## Minimal Embed Snippet

```html
<link rel="stylesheet" href="https://server-ip/hedge-expert-widget.css" />
<script
  src="https://server-ip/hedge-expert-widget.js"
  data-hedge-expert
  data-api-url="https://server-ip"
  data-title="HEDGE-ExpertAI"
  data-subtitle="IoT App Discovery Assistant"
  data-position="bottom-right"
  data-primary-color="#0ea5e9"
  data-width="400px"
  data-height="580px"
></script>
```

## Recommended Validation Prompts

1. `I need an app for monitoring energy consumption`
2. `Find me a smart building HVAC solution`
3. `Detect water leaks in buildings`
4. `enregy monitoring`

## What To Check

1. The widget opens and closes cleanly.
2. The assistant shows Thinking, then Typing, then streamed output.
3. The Recommended Context side pane appears with ranked app cards.
4. Copy response works.
5. Feedback buttons send `accept` or `dismiss` without UI errors.
6. Mobile layout expands full-screen and remains usable.

## Deployment Notes

1. Keep `/demo.html` as the public demo and acceptance-test page.
2. Keep the widget JS and CSS as the only production UI assets to embed elsewhere.
3. Do not maintain an extra `widget-demo.html` alias; it creates avoidable duplication.
4. If you need a branded host page, duplicate only the shell page, not the widget logic.