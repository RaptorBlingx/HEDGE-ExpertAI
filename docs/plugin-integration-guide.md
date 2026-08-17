# HEDGE-ExpertAI Widget Integration Guide

> **Integration status:** The widget is a v2 integration artifact for testing
> and delivery preparation. It is not yet approved or validated in the real
> HEDGE-IoT App Store. The final embedding, authentication, hosting, CSP/CORS,
> accessibility, localization, analytics and release process must be aligned
> with the HEDGE team.

## Overview

The widget is a standalone JavaScript/CSS component with no frontend framework
dependency. It calls the HEDGE-ExpertAI gateway over HTTPS and supports the v2
chat-streaming contract. The React console is a development/validation surface;
the widget is the intended App Store embedding artifact.

## Embed the widget

Add the stylesheet and script to an approved App Store page. Replace the example
origin with the approved HEDGE-ExpertAI gateway origin.

```html
<link rel="stylesheet" href="https://assistant.example/hedge-expert-widget.css" />
<script
  src="https://assistant.example/hedge-expert-widget.js"
  data-hedge-expert
  data-api-url="https://assistant.example"
  data-title="HEDGE-ExpertAI"
  data-subtitle="IoT App Discovery Assistant"
  data-position="bottom-right"
  data-locale="en"
></script>
```

The auto-initialization attributes support `api-url`, `title`, `subtitle`,
`position`, `primary-color`, `width`, `height`, `css-url`, and `locale`.
Supported locale values currently are `en`, `de`, `fr`, `es`, `it`, `nl`, `pt`,
and `tr`.

For a host that must provide a current access token, use explicit initialization:

```html
<script src="https://assistant.example/hedge-expert-widget.js"></script>
<script>
  new HedgeExpertWidget({
    apiUrl: "https://assistant.example",
    locale: "en",
    getAccessToken: () => getCurrentHedgeAccessToken(),
  });
</script>
```

The access-token callback is optional. The approved App Store identity and token
flow must be provided by HEDGE before a production configuration is chosen.

## Required v2 gateway endpoints

| Endpoint | Purpose |
|---|---|
| `POST /api/v2/chat/stream` | Main typed SSE conversation request. The widget sends `session_id`, `message`, `locale`, and `filters`. |
| `POST /api/v2/recommendation-events` | Best-effort, idempotent event for recommendation acceptance, dismissal, or App opening. |
| `DELETE /api/v2/sessions/{session_id}` | Removes the current operational session when the user clears the widget. |

The streaming response uses `text/event-stream` and contains JSON payloads with
the event types `stage`, `recommendations`, `explanation_delta`, `complete`,
and `problem`. Recommendation cards are displayed after the `recommendations`
event; validated explanation text follows through `explanation_delta` events.

## Runtime behavior

- A session identifier is kept in browser `sessionStorage`; it is not placed in
  cookies or in a URL.
- The widget can pass an `Authorization: Bearer` header only through the
  `getAccessToken` callback.
- Recommendation feedback and App-open events include an idempotency key.
- The widget supports cancellation, clearing/deleting an operational session,
  responsive layout, and localized interface labels.
- The gateway applies its configured security headers, CORS policy, rate limits,
  and authentication policy. The host page must permit the gateway origin in its
  CSP `connect-src` directive.

## HEDGE-side decisions required before final integration

1. Approved embedding mechanism and asset-hosting location.
2. Gateway origin, TLS termination, CSP/CORS and network/egress rules.
3. OAuth/OIDC or alternative identity flow, claims/roles, and token lifecycle.
4. App Store design system, accessibility, localization, responsive-layout, and
   browser-support requirements.
5. Authoritative URL/navigation behavior for recommended Apps.
6. Consent, telemetry, privacy, retention, release and operational-support
   requirements.

## Local demo only

The repository includes `demo.html` as a local smoke-test host page. It is not a
substitute for App Store embedding or security acceptance. See
`docs/architecture.md`, `docs/api-reference.md`, and the generated OpenAPI
contracts for the current backend boundaries.
