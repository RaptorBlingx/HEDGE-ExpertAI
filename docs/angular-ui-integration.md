# Angular ExpertAI integration boundary

This UI is based on the verified `f7ffc16` backend checkpoint. It changes presentation
only: Rasa, E5/hybrid retrieval, Qwen3 4B one-pass interpretation, suitability,
authorization, source preparation, synchronization and database schema are unchanged.

The [partner answers](integration-baseline.md#confirmed-store-v1-boundary) confirm
Angular, an inactive chat-like pane, open transport coordination and possible
portfolio/details representations of recommendations. No host Angular version,
design system or native interaction contract has been approved. The
[proposal](proposals/HEDGE-IoT-OC1-Proposal-HedgeExpertAI.md) defines the commitments;
this demonstration does not complete native partner integration or establish T2 KPIs.

## Stack decision, researched 2026-10-20

Registry versions were checked alongside primary documentation. Pins and transitive
dependencies are in the separate Angular lockfile.

The existing licence check additionally recognizes OFL-1.1 for the unmodified,
self-hosted Inter/Manrope font assets (notices distributed with the preview), and
the exact `(Apache-2.0 AND BSD-3-Clause)` expression used by the build-time protobuf
dependency. Both underlying permissive licences were already accepted. Other
licence restrictions and existing security gates remain in place.

| Candidate | Observed version | Decision |
| --- | --- | --- |
| Angular | 22.2.3 stable | Standalone components, signals, zoneless production AOT build. Node 24.22.0 / TypeScript 6.0.2 satisfy its current compatibility requirements. |
| Angular CDK / Aria | 22.2.3 | Use only CDK a11y focus primitives. Native buttons/details cover the remaining interactions; no composite Aria widget needed. |
| Tailwind CSS | 4.3.3 | Reviewed; scoped CSS and explicit tokens are sufficient, avoid a host-wide reset/build prerequisite. |
| spartan/ui | brain 1.8.0 | Reviewed; supports Angular 21–22 but brings Tailwind and additional peers. No need to copy a second style/component layer for this interface. |
| Lucide Angular | `@lucide/angular` 1.60.0 | Selected standalone icons, tree-shaken. Legacy `lucide-angular` 1.0.0 declares Angular peers only through 21 and was not selected. |

Sources: [Angular compatibility](https://angular.dev/reference/versions),
[release support](https://angular.dev/reference/releases),
[CDK focus utilities](https://material.angular.dev/cdk/a11y/overview),
[Angular Aria](https://angular.dev/guide/aria/overview),
[Tailwind Angular setup](https://tailwindcss.com/docs/installation/framework-guides/angular),
[spartan installation](https://www.spartan.ng/documentation/installation),
[Lucide Angular](https://lucide.dev/guide/angular/getting-started).

## Native host composition

Use the exports in `frontend/angular/src/public-api.ts` as native Angular source
components. The application bootstrap and demo shell are separate. No custom element,
iframe, nested Angular bootstrap or second Angular runtime is required.

```ts
import { ExpertAssistant, EXPERT_CONFIG } from './expertai/public-api';

// In the host component imports: [ExpertAssistant]
// In host APPLICATION providers (the API adapter is a root service):
// Illustrative user-token hook, not an M2M credential.
{
  provide: EXPERT_CONFIG,
  useValue: {
    apiBase: '', // host reverse proxy to ExpertAI
    sessionKey: 'host-expertai-session',
    getAccessToken: () => hostUserAuth.getAccessToken(),
  },
}
```

```html
<hedge-expert-assistant
  [style.display]="assistantVisible ? 'block' : 'none'"
  [presentation]="expanded ? 'workspace' : 'pane'"
  (expand)="expanded = true"
  (close)="assistantVisible = false"
/>
```

The parent must provide an explicit height/min-height and keep the component mounted
if it wants to preserve in-flight state while changing presentation. Theme tokens
live on the assistant host; a `[data-theme="dark"]` ancestor selects the default dark
palette. Override `--ea-*` tokens on the host for the agreed visual system. The demo's
fonts are optional; provide `--ea-font` / `--ea-heading` to inherit host typography.
This is a browser interface; an SSR host should mount it at its client boundary.

The host's Angular major and dependency sharing must be confirmed before native
adoption. This repository contains reusable source, not a published version-neutral
APF library. Align peers and package the entry point once the actual host workspace
and its policies are available. That is build/contract coordination, not a UI rewrite.

## Current service contract

| Request | UI use |
| --- | --- |
| `GET /api/v2/catalogue?offset=&limit=` | Current private workspace catalogue, native IDs/name/provider, pagination. |
| `GET /api/v2/status` | Source provenance label; no invented freshness or health metrics. |
| `POST /api/v2/chat/stream` | `{session_id,message,locale:'en',filters:{},app_action?}`; POST SSE, authenticated fetch. |
| `GET /api/v2/sessions/{id}` | Restore operational history and current App results. |
| `DELETE /api/v2/sessions/{id}` | Clear operational conversation context after confirmation. |

`stage`, `recommendations`, `explanation_delta`, `complete` and `problem` are consumed
without changing their meaning. A missing completion, malformed data, failed request
or terminal problem stays an error. Incoming text is escaped/sanitized. Metadata is
never interpreted as instructions.

Inspection sends `{type:'inspect',store_id,app_id}`. The server resolves it against
the current authorized catalogue. Display names do not replace identity. Comparison
uses the existing conversational request, since there is no typed comparison action
in the current API. It retains server suitability/constraint checks; the UI makes
no eligibility decisions. The component offers no invented install/open URL. A
future portfolio/detail navigation callback must use the native pair and an agreed
host route resolver, with accepted-event semantics coordinated separately.

`/api/v2/catalogue`, `/status` and history GET currently belong to the private Store
workspace gateway. They are **not a claimed public partner contract**. The typed
`ExpertApi` boundary can be supplied by the host (`provide: ExpertApi, useClass:
HostExpertApi`) when the agreed authorized catalogue/history surfaces differ.
Do not expose private gateway helpers to a public origin without the separate
authentication/authorization review. User-token authentication, cross-origin CORS,
SSE proxy timeouts, host CSP and portfolio event semantics remain coordination items.
Keycloak M2M credentials stay in the backend. The UI never acquires or stores them.

An iframe of the standalone UI could support an isolated early pilot, with approved
frame-ancestor/origin/session policy. It is an optional hosting arrangement, not a
second implementation. The private preview deliberately allows only same-origin
framing and loopback access.
