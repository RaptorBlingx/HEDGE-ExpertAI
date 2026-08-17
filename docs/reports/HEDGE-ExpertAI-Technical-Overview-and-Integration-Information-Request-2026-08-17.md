# HEDGE-ExpertAI — Technical Overview and App Store Integration Information Request

**Project:** HEDGE-ExpertAI — Context-Aware AI Discovery and Recommendation Assistant for the HEDGE-IoT App Store
**Prepared by:** A Arti Mühendislik
**Date:** 17 August 2026

## 1. Purpose

This document describes the current HEDGE-ExpertAI technical design and the App Store information required to prepare a correct integration. It is intended to support technical discussion with the HEDGE-IoT team.

The current development environment uses a synthetic catalogue and a provisional adapter contract. It is not connected to the HEDGE-IoT App Store API. Therefore, this document does not claim App Store compatibility, sandbox validation, production deployment, or achievement of project KPIs.

## 2. Technical design

HEDGE-ExpertAI is organized as a set of containerized services. An embeddable web widget communicates with a gateway API. The gateway coordinates conversational processing, recommendation generation, discovery and ranking, and catalogue ingestion.

```text
User
  |
  v
HEDGE-ExpertAI web widget
  |
  v
Gateway API
  |
  +--> Chat and Intent service
  |
  +--> Recommendation service
  |       |
  |       `--> Local language-model runtime
  |
  `--> Discovery and Ranking service
          |
          +--> PostgreSQL full-text search
          `--> Qdrant dense search

Catalogue source
  |
  v
Metadata Ingestion service --> PostgreSQL catalogue --> Qdrant search index
```

### Main components

| Component | Role |
|---|---|
| Web widget | Provides the user-facing chat interface and displays recommended Apps. |
| Gateway API | Provides the public API boundary and serves the widget assets. |
| Chat and Intent service | Processes user requests and maintains bounded conversation context. |
| Recommendation service | Produces concise explanations from the retrieved App metadata. |
| Discovery and Ranking service | Combines full-text and dense retrieval results and applies supported filters. |
| Metadata Ingestion service | Validates catalogue records, stores revisions, and coordinates search-index updates. |
| PostgreSQL | Stores authoritative catalogue and operational records. |
| Qdrant | Stores the derived dense-search index. |
| Valkey | Supports bounded session, cache, rate-limit, and asynchronous queue functions. |

## 3. Main flows

### Catalogue flow

1. The ingestion service receives catalogue data from its configured source.
2. Each record is validated against the internal metadata model.
3. Valid catalogue revisions are stored in PostgreSQL together with the work needed to update the search index.
4. The indexing worker updates the derived Qdrant search index.
5. A catalogue item is treated as searchable only after the derived-index update succeeds.

The current configured development source is synthetic data. The mapping to the HEDGE-IoT App Store catalogue must be based on the official Store contract.

### User query and recommendation flow

1. The widget sends a user request to the gateway API.
2. The Chat and Intent service processes the request and passes it to the Recommendation service.
3. The Discovery and Ranking service retrieves candidate Apps independently through PostgreSQL full-text search and Qdrant dense search, then combines the result sets.
4. The ordered App recommendations are returned to the widget.
5. The Recommendation service produces a concise explanation using the retrieved App metadata. The explanation is validated against the ordered results before it is sent to the user. When validation cannot be completed, the service uses an evidence-based fallback response.

The streaming API sends progress, recommendations, explanation text, completion, and problem events. This allows recommendations to be displayed before the explanation is complete.

### Semantic metadata

The internal metadata model supports semantic annotations, including optional SAREF-related information. Such information is used only as an additional retrieval/ranking signal. The expected HEDGE-IoT metadata field names, ontology version, URI/property format, and allowed use must be confirmed from the official Store contract.

## 4. Current development boundary

The current configuration includes a versioned provisional Store adapter contract and a synthetic catalogue for development and test work. The actual HEDGE-IoT API schema, authentication method, App Store metadata semantics, and front-end integration rules have not been supplied to this implementation.

The following items therefore remain outside the current verified scope:

- connection to the HEDGE-IoT App Store API or sandbox;
- validation against HEDGE App Store data;
- validation of the widget within the HEDGE App Store user interface;
- measurement of performance or catalogue freshness in a HEDGE environment;
- pilot-user and production-operation evidence.

## 5. Information requested from HEDGE-IoT

To prepare the integration correctly, we request the following information and support from the HEDGE-IoT App Store team.

### App Store access and API contract

1. Sandbox URL, access procedure, suitable test accounts, and a technical contact for integration questions.
2. Current API/OpenAPI documentation, base URLs, supported API versions, request/response examples, rate limits, error conventions, and permitted test operations.
3. Authentication method for App Store API access, including any OAuth/OIDC, service-account, token, role, or credential requirements.

### Catalogue data and updates

4. Catalogue schema, required and optional metadata fields, stable App identifiers, versioning, App detail/install URLs, and publication/update timestamps.
5. Expected behavior for pagination, filtering, unpublished Apps, deleted Apps, and catalogue updates.
6. Availability of webhooks or other change events, if any.
7. Any SAREF-aligned metadata exposed by the Store, including field names, ontology version, URI/property format, provenance, and representative examples.

### Widget and security integration

8. Approved widget integration method: script, web component, module/package, iframe, or contribution to the App Store frontend.
9. Asset-hosting, frontend release, CSP/CORS, browser-support, accessibility, localization, and navigation requirements.
10. Identity propagation, TLS/domain, logging, consent, privacy, and retention requirements applicable to the integration.

### Deployment and validation

11. Expected hosting boundary, container/orchestrator constraints, network/egress rules, compute/storage availability, and observability requirements.
12. A staging environment and representative sandbox dataset for integration testing.
13. A jointly reviewed query set for later retrieval and user-flow validation.

## 6. Proposed integration sequence

After receiving the requested Store-side information, the next technical actions are:

1. Map the official API and metadata schema to the integration adapter.
2. Configure the widget and gateway for the approved embedding, authentication, and security model.
3. Test catalogue synchronization, retrieval, recommendation display, streaming, and App navigation in the sandbox.
4. Record integration results and apply any required technical changes before a pilot or production deployment is considered.
