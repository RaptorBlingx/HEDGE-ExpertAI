# HEDGE-ExpertAI — Follow-Up Progress Report

**Project:** Context-Aware AI Discovery and Recommendation Assistant for the HEDGE-IoT App Store
**Acronym:** HEDGE-ExpertAI
**Beneficiary:** A Arti Mühendislik
**Open Call topic:** Topic 15 — AI-Enhanced Data App Discovery & Recommendation Engine
**Reporting date:** 12 July 2026
**Reporting reference:** M1 follow-up and System Architecture Specification review
**Dissemination:** Internal for Project Consortium

## 1. Executive summary

Work during the initial project period has focused on the proposal's M1 priorities: project setup, the technical architecture and data flow, KPI definition, integration planning, and preparation of the System Architecture Specification (D2.1).

D2.1 has been consolidated as a complete architecture baseline for consortium review. It defines the system context, component boundaries, principal data flows, interfaces, deployment model, security boundaries, SAREF-aligned ranking approach, KPI measurement points, and the outstanding HEDGE-IoT integration decisions.

The architecture has also been checked against a local reference implementation. This provides early feasibility evidence for the selected service boundaries, container topology, App Store adapter approach, hybrid retrieval path, and embeddable user-interface approach. These results reduce implementation risk but are not presented as completion of the mid-term prototype, sandbox validation, or final project KPIs.

M1 should be considered **ready for completion actions**, rather than completed, because the proposal defines M1 verification as delivery of D1.1 together with approval of the architecture document. D1.1 was not present in the audited project repository, and consortium approval of D2.1 remains to be obtained.

## 2. Proposal baseline for this follow-up

The approved proposal establishes the following initial priorities:

- M1 establishes the architecture and KPI baseline.
- Task 1 establishes project requirements, the KPI/TRL path, risks, IPR and ethics baselines, the HEDGE API-aligned architecture, sandbox access, repositories, and CI/CD.
- Task 2 begins the system design and functional core, including the chat and intent layer, metadata ingestion, discovery and ranking, SAREF-aligned signals where available, and a minimal front-end integration.
- M1, “Project Setup and Architecture Approval,” is verified through delivery of D1.1 and approval of the architecture document.
- D2.1 is the internal “System Architecture Specification.”

The proposal uses relative project months and does not state a calendar start date in the version available in the repository. This report therefore uses the M1 follow-up reference without assigning an unverified calendar-month mapping.

## 3. Progress against the current proposal scope

| Proposal obligation | Verified progress | Status at reporting date |
|---|---|---|
| Architecture and data-flow design | System context, service decomposition, request flow, ingestion flow, ranking flow, deployment topology, and external boundaries are defined in D2.1. | Complete for review |
| KPI baseline | Proposal targets for top-two relevance, response time, catalogue freshness, acceptance, explanation quality, and validation sessions are traced to architecture measurement points. | Complete for architecture stage |
| HEDGE App Store integration design | An adapter boundary, expected metadata mapping, scheduled synchronization flow, widget/API boundary, and mock-contract fallback are defined. | Design complete; official contract validation pending |
| SAREF standards alignment | SAREF-aligned metadata is treated as an optional ranking signal. The ranking API supports a bounded category-match boost, and the architecture specifies explicit metadata as the preferred source. | Ranking mechanism present; end-to-end propagation and HEDGE field semantics pending |
| Containerized and documented backend | Docker Compose topology, service health checks, configuration model, API documentation, deployment guidance, and Apache-2.0 licensing are present. | Verified locally at configuration level |
| Repository and CI/CD baseline | Repository structure and a GitHub Actions workflow for linting, tests, and image builds are present. | Present; coverage gate requires correction |
| D1.1 Project Management & IPR Handbook | No D1.1 document was found in the audited repository. | Required to close M1 |
| Architecture approval | D2.1 is prepared for review; no consortium approval record was found. | Approval pending |

## 4. D2.1 System Architecture Specification

D2.1 now covers the architecture content required to proceed with implementation and consortium review:

1. proposal-derived functional and non-functional drivers;
2. system context and trust boundaries;
3. modular service architecture and responsibilities;
4. conversational, recommendation, search, ingestion, and indexing flows;
5. App Store metadata model and external interface assumptions;
6. SAREF-aligned metadata handling and ranking behavior;
7. deployment, configuration, availability, and observability design;
8. security, privacy, and data-retention boundaries;
9. KPI instrumentation and validation approach;
10. risks, technical substitutions, open integration decisions, and requirement traceability.

The architecture retains the proposal's required behavior while documenting implementation choices that require consortium visibility:

- Qdrant with vector retrieval and application-layer lexical scoring is used in place of the proposal example of FAISS plus a separate inverted index.
- The ingestion service is consolidated in Python rather than split across Node.js and Python.
- RASA is included as the target intent-classification option, with a deterministic fallback for constrained environments; the resource profile and activation point require alignment with the target sandbox.

These choices preserve the proposal's functional intent—hybrid retrieval, modularity, continuous ingestion, explainability, and reproducibility—but should be accepted as part of the D2.1 review.

## 5. Selected early feasibility evidence

The following evidence is relevant to architecture confidence and is intentionally limited to items that support M1 and D2.1:

- A modular local service topology exists for the gateway, chat/intent processing, recommendation, discovery/ranking, and metadata ingestion functions.
- A development mock App Store service and configuration-based API adapter reduce the risk of delayed access to the official sandbox API, consistent with proposal risk R1.
- A lightweight embeddable widget and an OpenAPI-documented backend boundary demonstrate the intended integration pattern.
- Hybrid retrieval is implemented as a local proof of feasibility, and the ranking endpoint supports an optional SAREF-aligned category boost when the category is supplied.
- On 12 July 2026, the available automated test suite completed successfully.
- On 12 July 2026, the frontend TypeScript and production build completed successfully.
- Widget JavaScript syntax, Docker Compose configuration, and the checked OpenAPI JSON files passed structural validation.

This evidence does not establish HEDGE sandbox integration, real-catalogue correctness, end-to-end KPI compliance, user acceptance, explanation accuracy, or TRL advancement.

## 6. Integration topics for agreement with the HEDGE-IoT team

### 6.1 Official App Store API and sandbox

The local adapter currently assumes a paginated application endpoint and a conventional metadata mapping. The following information is required before the integration can be validated:

- official sandbox base URL and access procedure;
- authentication mechanism, token flow, roles, and credential handling;
- application list and detail endpoint paths;
- pagination, filtering, rate-limit, retry, and error conventions;
- canonical metadata schema, identifiers, versioning, timestamps, and deletion behavior;
- input/output dataset field structure;
- availability of change notifications, webhooks, or event triggers;
- sandbox test data and permitted test operations.

### 6.2 App Store plug-in integration

The following front-end constraints should be agreed:

- approved embedding method and asset-hosting location;
- content security policy and permitted connection origins;
- design-system, accessibility, localization, and responsive-layout requirements;
- authentication propagation from the App Store to the assistant;
- required navigation behavior from recommendations to App Store detail pages;
- telemetry and consent requirements for feedback and KPI measurement.

### 6.3 KPI acceptance protocol

The proposal targets need a shared measurement protocol covering:

- whether the response-time target applies to ranked results, time to first visible recommendation, time to first generated token, or the complete generated answer;
- the jointly labelled query set and relevance-judgement method;
- the definition of an accepted recommendation;
- the explanation-accuracy review rubric;
- the start and end points used for catalogue-freshness measurement;
- the infrastructure profile on which latency will be accepted.

## 7. SAREF alignment

The proposal requires SAREF-aligned fields to be used where available as optional ranking signals. The target architecture follows that requirement as follows:

- an explicit SAREF-aligned value supplied by the App Store is the preferred source;
- when no explicit value is available, a lightweight keyword-derived domain category may be used as a fallback signal;
- the signal supplements lexical and semantic relevance and is not a mandatory filter;
- explanations remain grounded in application metadata rather than presenting inferred categories as authoritative ontology assertions.

The current ranking implementation can apply the optional boost when a category is provided, but automatic fallback assignment for missing App categories and propagation of the query category through the complete chat flow are not yet implemented end to end. The mechanism is a standards-aligned ranking aid, not a complete RDF knowledge graph or formal ontology reasoner. The HEDGE-IoT team should confirm whether the App Store exposes SAREF class URIs, extension terms, properties, or another controlled vocabulary, and whether exact URI-level mappings are expected.

## 8. Items required to close the current milestone

| Action | Completion evidence |
|---|---|
| Finalize and deliver D1.1 | Project Management & IPR Handbook issued under document control |
| Review and approve D2.1 | Consortium review comments resolved and approval recorded |
| Confirm official project calendar | Grant-agreement start date and deliverable due dates recorded in the management baseline |
| Confirm sandbox access and API contract | Credentials/access, interface specification, and named technical contact available |
| Confirm SAREF metadata expectations | Agreed field names, identifiers/URIs, and fallback behavior |
| Confirm KPI measurement protocol | Written definitions for relevance, latency, freshness, acceptance, and explanation accuracy |
| Restore the configured coverage gate | CI run meets the configured 80% threshold or an approved core-module coverage scope is documented |

## 9. Quality and verification statement

The status statements in this report were checked against the approved proposal text, the current project documentation, the current implementation, and reproducible local validation commands. No claim is made for approval, public availability, real HEDGE-IoT sandbox operation, live App Store API compatibility, or final KPI achievement where corresponding evidence was not available.

Future deliverables—D2.2, D3.1, D4.1, and D4.2—are outside the claimed scope of this follow-up.
