# ExpertAI Angular prototype

An actual service-connected interface with two presentations: a discovery workspace
and a compact assistant pane. Both use the same `ExpertAssistant` instance and
conversation state. This is a standalone prototype, **not the official HEDGE App
Store frontend**. See the [integration contract](../../docs/angular-ui-integration.md).

## Build and preview

Use Node **24.22.0** and the committed lockfile. No global CLI is needed.

```bash
cd frontend/angular
npm ci
npm test
npm audit --audit-level=moderate
npm run build
# Existing gateway configured for this private preview, on loopback 8127:
EXPERT_BACKEND=http://127.0.0.1:8127 UI_PORT=8126 npm run demo
```

The server binds **127.0.0.1 only**. It streams API responses without buffering,
validates incoming Host/Origin, and maps the validated origin to the backend hop.
It forwards only the documented preview routes. It exposes no refresh/admin
operations and reads no secret files. Backend secrets belong in secure server
configuration. This server is a private demonstration aid, not a production edge.

`npm start` is an optional local Angular development server; configure a trusted
same-origin API proxy before connecting it to authenticated services. The
production preview above is the verified path.

## Browser checks

Use an existing Playwright installation and Chromium. Keep the evidence directory
outside Git: it contains real Store excerpts and complete conversations.

```bash
PLAYWRIGHT_MODULE_PATH=/path/to/playwright \
BROWSER_EXECUTABLE=/path/to/chromium \
ANGULAR_UI_URL=http://127.0.0.1:8126 \
node ../../evaluation/angular-ui/browser.cjs /private/evidence/real-ui
```

`evaluation/angular-ui/failure-checks.cjs` accepts the same environment and output
argument. It deliberately simulates unavailable services, invalid/truncated SSE and
unsafe markup for UI verification; those results are not real Store quality evidence.
The real-service script retains rendered screenshots, raw SSE and complete answers
for human review. It needs two authorized Apps for the comparison flow, does not
refresh/seed the Store, and clears only its own conversation session.

## Structure

- `src/lib/assistant.*`: reusable assistant, responsive layout, details and controls.
- `src/lib/app-card.*`: reusable native-identity App cards and comparison selection.
- `src/lib/conversation.ts`: per-assistant state, history, streaming lifecycle and clear.
- `src/lib/expert-api.ts`, `contracts.ts`, `sse.ts`: typed HTTP boundary and incremental SSE.
- `src/lib/answer.ts`: Markdown rendered through Angular sanitization; source HTML
  is escaped. No trust-bypass API is used.
- `src/lib/tokens.css`: scoped navy/teal theme and host-overridable tokens.
- `src/public-api.ts`: native Angular component/configuration exports, no bootstrap.
- `src/demo`: disposable host preview shell. No partner branding assets, fabricated
  catalogue data or App-specific answers are embedded in the shell.

Angular **22.2.3**, CDK **22.2.3** (focus management only), selected
`@lucide/angular` **1.60.0** icons and `marked` **18.1.1**. Signals, standalone
components, zoneless rendering, component CSS and container queries; no animation
framework, SSR server, custom-element runtime or global CSS reset. Two self-hosted
Latin variable fonts are demo assets; the host can provide its own typography.

## Behavior and limits

Cards initially show the catalogue's name/provider. Authoritative detail fields
arrive from real inspection/recommendation responses. The original evidence is
available in the App detail dialog. Merely appearing in the catalogue or a comparison
is not displayed as a recommendation. A “Documented match” label requires both a
recommended decision and source-supported suitability. No numerical score, free
pricing claim, installation action or unverified external link is manufactured.
Current response Apps appear first in the service's order, including Apps beyond
the loaded catalogue page. Remaining catalogue entries stay available for browsing.

The UI renders the service's complete text; it does not rewrite AI answers.
Prepared vs assisted labels reflect terminal generation metadata. A slow-request
indicator uses elapsed time, not fabricated model progress. The current Store
backend emits prepared text in one SSE delta after it has completed its work;
the UI also supports incremental deltas when the service supplies them.

One conversation is restored per browser tab using an origin-specific session ID
in sessionStorage; conversation contents are not stored in browser persistence.
Presentation switches preserve the component/session. Clearing waits for the server
to confirm operational state deletion. Persistent, privacy-minimized acceptance
events retain the existing backend retention behavior. Stop cancels the browser
request; an already-started server/model operation may finish. Retrying a request
after a broken connection can repeat a turn; no unsupported exactly-once guarantee
is made. Cleared conversations, invalid/truncated SSE and service failures are not
replaced with demo content.

Keyboard: Enter sends, Shift+Enter adds a line; IME composition is respected.
Details and clear dialogs trap/restore focus and close with Escape. The embedded
pane is nonmodal and leaves the host available. Native buttons, labelled controls,
live status, visible focus and reduced-motion support are included. Desktop,
tablet and mobile visual/browser evidence is recorded outside Git; this does not
claim a full assistive-technology or WCAG conformance audit.
