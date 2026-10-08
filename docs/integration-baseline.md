# HEDGE Store integration baseline

Prepared 2026-10-08 against repository commit `fa06952`. This is the current
integration planning entry point; live integration and acceptance remain pending.
Phase 1 offline metadata and identity support is now implemented locally; see
the [implementation notes](store-v1-phase1.md) for mapping, persistence,
verification and assumptions. Live integration and acceptance remain pending.
Keep it current as decisions are approved, and link to detailed guides instead
of copying them here.

## Evidence and authority

- **Project commitments:** [proposal](proposals/HEDGE-IoT-OC1-Proposal-HedgeExpertAI.md), especially objectives 1–5.
- **HEDGE answers:** supplied `HEDGE_ExpertAI_—_Essential_Integration_Questions_repliedFCoelho.docx`, §§1.1–3.1. The supplied file is currently an untracked local source; the confirmed facts below retain its relevant answers without altering that working material.
- **Observed external contract:** [Store documentation](https://store.haslab-dataspace.pt/docs/index.html), [Swagger UI](https://store.haslab-dataspace.pt/backend/api/v1/swagger-ui/index.html), and [raw OpenAPI](https://store.haslab-dataspace.pt/backend/api/v1/api-docs), retrieved read-only on 2026-10-08. OpenAPI 3.0.1, `info.version: 1.0`; fetched SHA-256 `f5090c9cad06ea314a70ca1676dc433d97006ddbd7a65f9273058480239793a3`. No authenticated catalogue payload or end-to-end integration was validated, and no full specification snapshot is retained here.
- **Implementation evidence:** current code and Git history; [architecture](architecture.md), [configuration](configuration-reference.md), and [traceability](traceability-matrix.md). Historical reports and local test results do not supersede these external answers or prove production KPIs.

## Confirmed Store v1 boundary

Use HTTPS base `https://store.haslab-dataspace.pt/backend/api/v1` with these
relative paths. ExpertAI's own `/api/v2` is a separate version namespace.

| Operation | Method and relative path | Documented successful response |
|---|---|---|
| `getAllApps` | `GET /store/{appStoreId}/app/all` | Array of `App`; UI-oriented catalogue |
| `getApp` | `GET /store/{appStoreId}/app/{appId}` | `App` |
| `getAssets` | `GET /dsp/connector/asset/all` | Array of `AssetRequest`; Dataspace asset descriptions |

All three declare a required `Authorization` header. HEDGE offers a Keycloak
client/token used as Bearer for backend access; Store Keycloak is separate from
Dataspace authentication. The generated OpenAPI server URL uses HTTP: use the
deployed HTTPS origin, and avoid doubling `/api/v1` when composing paths.

| Topic | Confirmed fact and limit |
|---|---|
| Version/identity | HEDGE requests v1 and expects notified minor updates. Native identity is **Store ID + App ID**. Supplied Store ID: `56779afa-bdcc-4abe-a8b0-d306dc07bed1`; make it configuration, not a global identity assumption. |
| Metadata | `App` exposes `appId`, `fkAppStoreId`, `name`, `description`, `provider`, `readme`, `active`, `visible`, `registrationDate`, URLs, and `appVersionList`. `AssetRequest` has `@id`, `@type`, `@context`, `properties`, and `dataAddress`; properties include categories and features. Neither supplies ExpertAI `schema_version: 2.0`. |
| Guarantees | The reply says sections are guaranteed, with extensible asset metadata. OpenAPI declares no required-property lists for these models: confirm usable payloads before enforcing field presence. Do not infer translations, SAREF annotations, licences, canonical detail links, or an App/asset join. `registrationDate` is not a last-update timestamp. |
| Publication | In HEDGE there is no certification routine; newly created Apps become not-visible until the owner publishes them. Owner-only records must not enter public recommendations. The exact meaning of `active` and service-client visibility still needs confirmation. |
| Synchronization | No webhooks/update notifications; HEDGE recommends daily polling. A Unix last-update timestamp was **offered**, not confirmed as deployed. No pagination limit or API rate limit was reported in the reply; this is not a throughput guarantee. |
| Frontend | Store uses Angular and prefers its existing, currently inactive chat-like pane. REST, pub/sub, and streaming remain open. Ranked portfolio results, explanations on details, and recommendation badges were suggested; no widget embedding contract was approved. |
| Identity/hosting | User OIDC is conditional on user-specific recommendations, not required for generic catalogue discovery. Co-hosting is preferred; separately hosted A Arti HTTPS is allowed. The DMZ answer is incomplete, so hosting conditions are unresolved. |
| Testing | No staging existed at reply time; a dummy Store with Apps can be provisioned. The reply's test-only catalogue and forthcoming real data describe that time, not verified current contents. |

## Initial implementation direction

These are repository planning decisions, not additional HEDGE approvals:

- Keep the existing services, PostgreSQL projection/outbox, Qdrant, Valkey,
  Rasa, Ollama, and gateway. Put Store-specific transport and normalization at
  the [ingestion client boundary](../services/metadata-ingest/app/client.py).
- Start with generic recommendations over publicly eligible Apps. Establish
  `getAllApps` identity/publication mapping first; add `getAssets` enrichment
  only once its join and access semantics are verified. Preserve native IDs
  and source provenance. Missing optional metadata stays missing; SAREF is an
  optional ranking signal, as committed in the proposal.
- Keep synthetic fixtures useful, but distinguish their rich
  [model](../shared/hedge_shared/models_v2.py) and
  [schema](../contracts/hedge-store-v2.schema.json) from the Store source
  profile. Do not fabricate fields to make real records pass fixture validation.
- Offer a small typed result contract through the existing gateway for the
  agreed native UI surface. Keep the widget as a demo/alternative pending
  approval. Do not add a second gateway, frontend framework, webhook bus,
  personalization system, or orchestration platform for initial integration.
- Reconcile daily polling with the proposal's **≤2-hour** publication-to-search
  target before choosing a production schedule. The proposal also mentions a
  ≤24-hour outer target; neither a two-hour timer nor daily polling proves
  measured freshness or authorizes weakening the commitment.

## Dependencies and implementation order

Split each phase into focused, reviewable changes with the exit evidence below.
Offline mapping can begin before credentials; live ingestion depends on both
contract examples and safe reconciliation. Separate transport from reconciliation
changes, and outbox recovery from retrieval safety fixes.

| Priority | Work and boundary | Exit evidence |
|---|---|---|
| 1 — prerequisite | Define the minimal Store source profile and explicit mapping at the client/shared-model boundary. Preserve Store/App identity and public eligibility; accommodate absent optional metadata without weakening synthetic validation globally. | Contract fixtures for sparse and rich Apps, duplicate App IDs across Stores, unknown fields, unpublished Apps, and malformed records; document assumptions pending payload confirmation. |
| 2 — prerequisite | Implement v1 HTTPS transport and outbound Bearer credentials. Correct guessed `/api/apps` routes and pagination. Make [snapshot reconciliation](../services/metadata-ingest/app/tasks/ingest.py) source-scoped, serialized, and deletion-safe before live use. | Mocked auth/renewal/error tests; failed, partial, quarantined, and unexpected-empty snapshots cannot erase unrelated or previously valid records; visibility withdrawal tested. Then validate read-only authenticated access on an agreed Store. |
| 3 — safety gate | Close existing [outbox/storage](../shared/hedge_shared/storage.py) and [retrieval](../services/discovery-ranking/app/searcher_v2.py) gaps: reclaim stalled work, handle exhausted retries, reject stale revisions, reindex reactivation, and verify final results against current public catalogue state. | Crash/replay/reordered-update tests; withdrawn Apps cannot escape through stale vectors or cache; lexical retrieval remains usable during vector lag. |
| 4 — native UI | Agree one UI surface and request/result/navigation contract; reuse gateway and dialogue flows. Specify native IDs, ordering, grounded explanations, terminal errors, and telemetry semantics. | Dummy-Store flow through Angular UI → gateway → current catalogue; browser/auth/CORS and error-path checks. SSE only if agreed; widget checks do not establish native UI acceptance. |
| 5 — hardening/validation | Validate the chosen host and production profile, secrets, TLS, monitoring, recovery, real models, and bounded load. Align corpus rights and evaluation protocols. | Retained target-environment evidence and reviewed acceptance results, linked from traceability; deterministic E2E and health checks alone are insufficient. |

## Questions still requiring HEDGE coordination

1. Provision the backend client: token endpoint, issuer/audience/scopes, lifetime,
   renewal/rotation, and visibility permissions. Provide representative
   authenticated App/asset payloads, including unpublished and withdrawn cases;
   confirm `active`, visibility filtering, asset-to-App join, and approved links.
2. Confirm whether last-update timestamps exist, their units/change semantics,
   and an acceptable polling cadence consistent with the proposal's freshness
   target. Do not wait for webhooks that are not provided.
3. Select the first native UI surface, transport, request/result fields, navigation,
   and incoming assistant access policy. Generic discovery does not itself
   justify collecting user identity. No extra design constraints were prescribed
   in the reply; normal accessibility/security validation still applies.
4. Agree hosting/network/resources, secrets and operational ownership; complete
   the unfinished DMZ conditions. Provision the offered dummy Store and assign
   a technical integration contact.
5. Agree public corpus permissions and acceptance protocol: ≥50 jointly labelled
   queries, HitRate@2 ≥70%, average response <5 seconds (report median separately),
   ≥70% accepted sessions, ≥80% human-reviewed contextual accuracy, and ≥10
   complete sessions. Define denominators, timing boundaries, and retained
   evidence before declaring success. See [evaluation guide](evaluation-and-testing.md)
   and [traceability](traceability-matrix.md); no KPI is newly marked achieved here.
