# Angular prototype verification — 2026-10-20

Based on backend checkpoint `f7ffc16`; local branch `feat/t2-angular-ui`.
The UI changes no backend services, schema, inference settings or Store data.
The existing demonstrations on 8096, 8106 and 8116 remain separate.

## Actual service-boundary evaluation

The production Angular build ran through its private loopback proxy, a separate
frozen `f7ffc16` gateway/chat/Expert stack and its own session PostgreSQL/Valkey.
Only that database received migrations 0001–0005. It reused the existing authorized
Store synchronization, Rasa, E5/Qdrant and Qwen3 4B inference services. No fixture
catalogue, in-process adapter, extra model download or 2B fallback was used.
The Store supplied **two Apps**, EdgeConnect and Semantic Treehouse.

The final ten-turn replay completed all SSE responses with **zero browser errors**.
Complete raw answers, events and screenshots are retained privately outside Git;
the following are observed flows, not a claim of a new recommendation-quality KPI.

| Flow exercised through real UI controls | Observed outcome |
| --- | --- |
| Catalogue starting action | Listed both real Apps and their prepared purposes. |
| Explain card action | Sent native Store/App inspection identity; explained EdgeConnect. |
| “Who provides it?” | INESCTEC, retained EdgeConnect context. |
| Make it simpler | Rendered the existing simpler explanation about combining participants’ offers. |
| App detail / source evidence | Showed actual metadata and complete projected README evidence. |
| Select two Apps / Compare | Explained their different documented jobs and asked which fits the need. |
| Reload | Restored the same operational conversation and provider answer. |
| “List only free applications.” | Explained that listed zero does not establish free use and offered alternatives. |
| Natural problem about partners’ different data names/formats | One Qwen interpretation; recommended Semantic Treehouse with source-supported suitability. |
| Provider follow-up | TNO, retained Semantic Treehouse context. |
| Mobile App detail | Read real Semantic Treehouse information through the compact pane. |
| Clear conversation | Confirmed server clear and returned to onboarding. |

Prepared responses were approximately **0.2–0.4 s** in the measured final browser
run. The assisted turn was **7.7 s**, one model call; an earlier first request with
a cold model was **52.1 s**. These are CPU-VM observations, not production latency
guarantees. The UI does not conceal cold loading or rewrite model outcomes.
Current response Apps are shown first in server order; catalogue entries remain
browsable and are not labelled recommendations. The documented-match badge requires
the backend's positive decision and source-supported suitability.

## Presentation and failure checks

Desktop 1440 px, tablet 768 px, mobile 390 px, and additional 320/1280 px overflow
checks were inspected. Light/dark, expanded/pane, App evidence, comparison, loading,
slower response, error recovery and clear states were captured. Mobile composer
remains visible and uses 16 px input text; presentation changes preserve the same
assistant instance and session. The final static artifact was separately opened
and smoke-tested after freezing it outside the working tree.

Separate, explicitly **simulated transport/UI** checks verified visible catalogue
and chat outages, real reload/retry recovery, native-action retention on retry,
truncated SSE handling, escaped source HTML/sanitized Markdown, stop and
elapsed-time states, Tab focus containment/restoration, reduced motion and rejection
of foreign-origin proxy POSTs. These checks are not live Store recommendation evidence.
The SSE unit checks cover split UTF-8/CRLF frames, malformed and incomplete data; native identity
checks prevent display-name/identifier concatenation collisions.

## Build, dependencies and startup

`npm ci`, the three focused boundary unit checks, production AOT build and the
existing licence checker passed. Full **and production-only npm audits report zero
vulnerabilities** for the new Angular lockfile. The existing console and backend
security checks were retained. The new CI job runs these Angular checks on its own
pinned Node version; no remote UI-branch CI run is claimed because it is not pushed.

The final JS is approximately **347 kB raw / 88 KiB gzip**, with approximately
**72 KiB** of self-hosted fonts. No remote fonts, analytics, visual framework or
animation library is requested at runtime. The private static server negotiates
precompressed assets while leaving SSE unbuffered. One fresh local-browser startup
recorded first contentful paint at **428 ms**; this is a VM-loopback observation,
not an SSH/WAN performance benchmark.

## Limits and integration handoff

- Only two real Apps are available. Pagination and off-page response composition
  are implemented; this evaluation does not establish large-catalogue quality.
- Backend semantic misses and CPU inference/cold-load limits remain. This frontend
  pass deliberately leaves AI policy and model behavior unchanged.
- App URLs, installation, confirmed pricing and numerical ranking are not invented.
- Stop cannot guarantee cancellation of an already-started server/model operation;
  retry after an interrupted connection may repeat a turn.
- Browser checks are not a full screen-reader/WCAG audit.
- Partner Angular version, authorized production catalogue/history endpoints,
  CSP/authentication, host navigation and acceptance-event semantics still require
  coordination. See the [native integration contract](angular-ui-integration.md).

Reproduction and browser commands are in the [Angular README](../frontend/angular/README.md).
Private deployment recovery instructions and source/artifact manifests are retained
with the isolated runtime, without committing secrets or Store snapshots.
