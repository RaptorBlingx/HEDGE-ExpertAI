# HEDGE Open Call 1 — First Meeting Brief (HEDGE-ExpertAI)

## Purpose of this document

This document prepares a safe, proposal-aligned narrative for the first coordination meeting with the HEDGE Open Call 1 team.

- **Source of truth:** proposal commitments.
- **Practical input:** current implementation status in this repository.
- **Meeting strategy:** speak in terms of "what we will deliver" (proposal language), while internally tracking what is already implemented.

---

## 1) Project positioning (proposal-aligned talk track)

### What HEDGE-ExpertAI is

HEDGE-ExpertAI is a context-aware AI assistant for the HEDGE-IoT App Store that helps users discover relevant apps using natural language and receive short, source-grounded explanations.

### What we will deliver (as committed)

1. A conversational assistant integrated with the App Store user flow.
2. Automated metadata ingestion and indexing from official App Store APIs.
3. A hybrid discovery/ranking engine (keyword + semantic similarity, with optional SAREF signals).
4. An LLM-powered recommendation/explanation layer.
5. A plug-in style frontend integration and OpenAPI-documented backend.
6. Reproducible documentation, test/evaluation assets, and containerized deployment.

---

## 2) Commitment matrix: proposal vs implementation status

Legend:
- **Committed in proposal:** yes/no
- **Status now:** implemented / partially implemented / pending
- **Meeting phrasing:** recommended wording for safe communication

| Area | Committed in proposal? | Status now (internal) | Meeting phrasing (safe) | Note |
|---|---|---|---|---|
| Conversational query endpoint and intent routing | Yes | Implemented | "We will provide a conversational assistant that interprets user needs and routes to discovery/recommendation services." |  |
| Hybrid retrieval (keyword + semantic) | Yes | Implemented | "We will use hybrid retrieval to improve relevance for non-expert user queries." |  |
| LLM-based recommendation explanations | Yes | Implemented | "We will generate concise, source-grounded explanations for recommendations." |  |
| SAREF-aligned ranking signals | Yes (optional) | Implemented | "We will leverage SAREF-aligned metadata where available as optional reinforcement signals." |  |
| Automated ingestion/index update pipeline | Yes | Implemented | "We will maintain freshness through automated ingestion and indexing." |  |
| Containerized microservice architecture | Yes | Implemented | "We will deliver a modular containerized architecture for deployment and reproducibility." |  |
| API gateway + OpenAPI exports | Yes | Implemented | "We will expose OpenAPI-documented services suitable for integration/testing." |  |
| Embeddable JS/CSS widget | Yes (plugin integration) | Implemented | "We will package delivery as an App Store-compatible plugin/widget integration." |  |
| Internal validation console (React app) | No (not explicitly required) | Implemented | "We use an internal validation interface to accelerate testing and demonstration." | **Extra beyond explicit proposal wording** |
| Dedicated mock App Store API service | Indirectly implied (risk mitigation) | Implemented | "To de-risk integration, we use a mock API contract environment before full sandbox wiring." | **Extra implementation detail** |
| Celery/Redis async orchestration | Not explicitly required | Implemented | "We use asynchronous job orchestration to support robust ingestion and update flows." | **Extra implementation detail** |
| Nginx packaging path for widget delivery/demo | Not explicitly required | Implemented | "We maintain a deployment-ready delivery path for widget hosting and integration tests." | **Extra implementation detail** |
| Evaluation scripts + labeled query set | Yes | Implemented | "We will validate relevance and quality with a reproducible query benchmark." |  |
| CI-oriented unit/integration test suite | Indirectly committed (quality/reproducibility) | Implemented | "We will maintain automated testing to support stable iterative delivery." | **Stronger than minimum commitment** |

---

## 3) What to present in the meeting (recommended structure)

### A. Vision (high-level)
- Problem: non-expert users struggle to find the right IoT apps in growing catalogues.
- Solution: conversational discovery + explainable recommendations + continuously updated metadata index.
- Value: better findability, lower discovery friction, standards-aware ranking (SAREF).

### B. Work packages (proposal language)
- Functional AI core (chat, ranking, recommendation).
- Ingestion/indexing automation.
- App Store integration package (plugin + APIs).
- Validation against KPI-oriented test scenarios.

### C. KPI framing
- Relevance target: top-2 relevance at or above proposal target.
- Latency target: continue optimization toward proposal threshold.
- Freshness target: continuous updates within required delay window.

### D. Collaboration ask to HEDGE team
- Confirm API/sandbox access path, credentials, and update/webhook capabilities.
- Confirm any UI/plugin constraints for final App Store embedding.
- Confirm evaluation protocol for final acceptance.

---

## 4) Optional talking points (use only if strategically useful)

These are **already implemented** but can be kept as timing advantages if needed:

1. Internal validation console for rapid demo/testing loops.
2. Contract-first mock API environment for integration de-risking.
3. Async ingestion orchestration (Celery/Redis) for reliable scheduled updates.
4. Extended documentation set (deployment/security/config/API/developer guides).
5. Standalone widget demo delivery path.

---

## 5) Suggested speaking style for the meeting

Use future-oriented, commitment-safe wording:
- "We are building / we will deliver / we are targeting..."
- Avoid over-committing beyond proposal KPIs.
- If asked about maturity, state that architecture and implementation tracks are progressing in line with proposal milestones and validation plan.

---

## 6) Evidence map (repository pointers)

- Proposal source: `docs/proposals/HEDGE-IoT-OC1-Proposal-HedgeExpertAI.md`
- Architecture and service decomposition: `docs/architecture.md`, `docs/services-guide.md`
- Public positioning and stack summary: `README.md`
- Widget/plugin assets: `frontend/widget/`
- Core services:
  - `services/chat-intent/`
  - `services/expert-recommend/`
  - `services/discovery-ranking/`
  - `services/metadata-ingest/`
  - `services/gateway/`
  - `services/mock-api/`
- Evaluation assets: `evaluation/`, `tests/`
- OpenAPI exports: `docs/openapi/`

