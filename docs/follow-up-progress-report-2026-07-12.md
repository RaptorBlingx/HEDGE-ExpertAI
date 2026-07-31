# HEDGE-ExpertAI — Follow-Up Progress Report

**Project:** Context-Aware AI Discovery and Recommendation Assistant for the HEDGE-IoT App Store
**Acronym:** HEDGE-ExpertAI
**Beneficiary (per repository proposal file):** A Arti Mühendislik
**Open Call topic (per repository proposal file):** Topic 15 — AI-Enhanced Data App Discovery & Recommendation Engine
**Reporting date:** 12 July 2026
**Reporting reference:** M1 follow-up and System Architecture Specification review
**Dissemination:** Internal for Project Consortium
**Version:** 1.1 — evidence-corrected and last verified 13 July 2026

## 1. Executive summary

Repository artifacts reviewed for this follow-up address the proposal's M1 priorities: project setup, the technical architecture and data flow, KPI definition, integration planning, and preparation of the System Architecture Specification (D2.1).

D2.1 has been prepared as an architecture baseline for consortium review. It documents the system context, component boundaries, principal data flows, interfaces, deployment model, security boundaries, SAREF-aligned ranking approach, KPI measurement points, and the outstanding HEDGE-IoT integration decisions. Whether it is complete or acceptable is a consortium review decision and is not claimed in this report.

The documented architecture was checked against the reference implementation contained in the pushed report commit. This provides local feasibility evidence for the selected service boundaries, container topology, App Store adapter approach, hybrid retrieval path, and embeddable user-interface approach. It is not evidence of completion of the mid-term prototype, sandbox validation, or final project KPIs.

M1 must not be reported as completed from the repository evidence. The proposal file defines M1 verification as delivery of D1.1 together with approval of the architecture document. D1.1 was not present in the audited project repository, and no consortium approval record for D2.1 was found.

## 2. Proposal baseline for this follow-up

The proposal version stored in the repository establishes the following initial priorities. The repository does not contain a signed approval record or grant-agreement copy, so this report does not independently verify that this file is the controlling approved version:

- M1 establishes the architecture and KPI baseline.
- Task 1 establishes project requirements, the KPI/TRL path, risks, IPR and ethics baselines, the HEDGE API-aligned architecture, sandbox access, repositories, and CI/CD.
- Task 2 begins the system design and functional core, including the chat and intent layer, metadata ingestion, discovery and ranking, SAREF-aligned signals where available, and a minimal front-end integration.
- M1, “Project Setup and Architecture Approval,” is verified through delivery of D1.1 and approval of the architecture document.
- D2.1 is the internal “System Architecture Specification.”

The proposal uses relative project months and does not state a calendar start date in the version available in the repository. This report therefore uses the M1 follow-up reference without assigning an unverified calendar-month mapping.

## 3. Progress against the current proposal scope

| Proposal obligation | Verified progress | Status at reporting date |
|---|---|---|
| Architecture and data-flow design | System context, service decomposition, request flow, ingestion flow, ranking flow, deployment topology, and external boundaries are documented in D2.1. | Documented; no approval record found in the audited repository |
| KPI baseline | Proposal targets for top-two relevance, response time, catalogue freshness, acceptance, explanation quality, and validation sessions are traced to architecture measurement points. | Documented; acceptance definitions pending |
| HEDGE App Store integration design | An adapter boundary, expected metadata mapping, scheduled synchronization flow, widget/API boundary, and mock-contract fallback are defined. | Documented; official contract validation pending |
| SAREF standards alignment | SAREF-aligned metadata is treated as an optional ranking signal. The ranking API supports a bounded category-match boost, and the architecture specifies explicit metadata as the preferred source. | Ranking mechanism present; end-to-end propagation and HEDGE field semantics pending |
| Containerized and documented backend | Docker Compose topology, service health checks, configuration model, API documentation, deployment guidance, and Apache-2.0 licensing are present. | Verified locally at configuration level |
| Repository and CI/CD baseline | Repository structure and a GitHub Actions workflow for linting, tests, and image builds are present. | Present; the pushed snapshot fails the currently resolved Ruff lint command and the configured 80% coverage gate |
| D1.1 Project Management & IPR Handbook | No D1.1 document was found in the audited repository. | Required to close M1 |
| Architecture approval | D2.1 is prepared for review; no consortium approval record was found. | Approval status not evidenced in the audited repository |

## 4. D2.1 System Architecture Specification

D2.1 documents the following architecture topics for implementation planning and consortium review:

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
- On 13 July 2026, an isolated checkout of pushed commit `146c2a5` was tested in a clean Python 3.11.15 container: 152 tests passed. These are repository tests with mocked or in-process integration coverage; they are not a live deployed-system or HEDGE sandbox test.
- On 13 July 2026, `npm ci` and the frontend TypeScript/Vite production build completed successfully against the pushed commit.
- On 13 July 2026, the widget JavaScript syntax and Docker Compose configuration checks passed; all six committed OpenAPI files parsed as JSON and declare OpenAPI 3.1.0. This was not a full OpenAPI conformance or synchronization test.
- On 13 July 2026, the configured Ruff command, with the then-current unpinned Ruff 0.15.21, reported 20 lint errors. The exact CI unit-test command passed 120 tests but reported 58.70% coverage and correctly failed the configured 80% threshold.
- Regenerating OpenAPI from the pushed runtime changed four of the six committed exports and exposed missing streaming/recorded-session paths plus a stale health description. Even the regenerated streaming paths do not accurately declare their SSE media type, so API-contract synchronization remains open.

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
- explanations are intended to remain grounded in application metadata rather than presenting inferred categories as authoritative ontology assertions; explanation accuracy still requires validation.

The current ranking implementation can apply the optional boost when a category is provided, but automatic fallback assignment for missing App categories and propagation of the query category through the complete chat flow are not yet implemented end to end. The mechanism is a standards-aligned ranking aid, not a complete RDF knowledge graph or formal ontology reasoner. The HEDGE-IoT team should confirm whether the App Store exposes SAREF class URIs, extension terms, properties, or another controlled vocabulary, and whether exact URI-level mappings are expected.

## 8. Formal M1 verification and supporting readiness actions

The proposal lists only delivery of D1.1 and approval of the architecture document as the formal means of verifying M1. The remaining items below are supporting readiness actions and must not be misrepresented as additional formal milestone criteria unless the controlling project documents say otherwise.

### 8.1 Formal M1 verification

| Action | Completion evidence |
|---|---|
| Finalize and deliver D1.1 | Project Management & IPR Handbook issued under document control |
| Review and approve D2.1 | Consortium review comments resolved and approval recorded |

### 8.2 Supporting readiness and open actions

| Action | Completion evidence |
|---|---|
| Confirm official project calendar | Grant-agreement start date and deliverable due dates recorded in the management baseline |
| Confirm sandbox access and API contract | Credentials/access, interface specification, and named technical contact available |
| Confirm SAREF metadata expectations | Agreed field names, identifiers/URIs, and fallback behavior |
| Confirm KPI measurement protocol | Written definitions for relevance, latency, freshness, acceptance, and explanation accuracy |
| Meet or formally revise the configured coverage criterion | CI run meets the configured 80% threshold, or an approved core-module scope/threshold is documented |
| Resolve current lint findings | The configured Ruff command passes against a frozen, pinned tool version |

## 9. Quality and verification statement

The status statements in this corrected report were checked against the proposal file and artifacts stored in pushed commit `146c2a5`. The exact snapshot was re-tested on 13 July 2026. The original test counts were corrected because they had been measured from an uncommitted working tree rather than from the pushed snapshot. The GitHub repository, audited branch, and commit were independently accessible without authentication on 13 July 2026; this establishes public visibility, not consortium release approval or rights clearance.

An earlier repository progress note describes D1.1, D2.1, D2.2, and D3.1 as done and reports sandbox/evaluation results. A D3.1 file also declares a PASS. The audited repository contains no D1.1 deliverable, D2.1 approval record, signed controlling proposal, or retained raw execution evidence sufficient to substantiate those status claims. They are not relied upon here and require project-document-control confirmation.

No claim is made that the repository proposal file is the signed controlling version, that D2.1 has been approved, that the HEDGE-IoT sandbox is operational, that the implementation is compatible with the live App Store API, or that final KPIs have been achieved.

Other proposal deliverables—D2.2, D3.1, D4.1, and D4.2—are outside the scope assessed by this follow-up; no status conclusion about them is made here.
