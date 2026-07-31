# HEDGE Open Call 1 - 10 Minute Presentation Script

Purpose: first coordination meeting for HEDGE-ExpertAI.

Recommended timing: 7.5 to 8.5 minutes of speaking, with buffer for questions.

Important speaking style:
- Use "we will", "we are building", "we plan", and "our target is".
- Do not say that parts are already implemented.
- Keep the tone confident, friendly, and aligned with the proposal.

---

## Slide 1 - Title

### Slide Content

**HEDGE-ExpertAI**

Context-Aware AI Discovery and Recommendation Assistant  
for the HEDGE-IoT App Store

**Topic 15:** AI-Enhanced Data App Discovery & Recommendation Engine

**A Arti Muhendislik**

### Script

Hello everyone, and thank you for having us today.

My name is [your name], and I will present our project, HEDGE-ExpertAI.

The main idea is simple. We want to make the HEDGE-IoT App Store easier to search and easier to understand, especially for users who are not technical experts.

Today I will explain the problem, our solution, the planned system flow, our KPIs, and the points where we would like to align with the HEDGE team.

---

## Slide 2 - The Problem

### Slide Content

**Current Challenge**

- App catalogues can grow fast
- Users may not know the right keywords
- Similar apps can use different wording
- Good apps may be hard to find
- Non-expert users need simple guidance

### Script

The problem we address is app discovery.

When an App Store grows, it becomes harder for users to find the right application. This is more difficult when users do not know the exact technical words, or when apps describe similar functions in different ways.

For example, one user may search for "energy saving", another may search for "electricity monitoring", and another may say "I want to reduce building consumption". These can be connected needs, but normal keyword search may not always understand this.

So our goal is to help users describe their need in simple language, and then guide them to relevant apps.

---

## Slide 3 - Our Solution

### Slide Content

**HEDGE-ExpertAI Solution**

- Conversational assistant for the App Store
- Natural language app discovery
- Hybrid search: keyword + semantic matching
- Optional SAREF-aligned ranking signals
- Short explanations based on app metadata
- Continuous metadata ingestion and indexing

### Script

Our solution is HEDGE-ExpertAI, a conversational assistant for the HEDGE-IoT App Store.

The assistant will allow users to write a normal question or request. It will understand the need, search the catalogue, rank the most relevant apps, and return recommendations.

The search will combine keyword matching with semantic matching. So the system can understand meaning, not only exact words. Where SAREF-aligned metadata is available, we will also use it as an extra ranking signal.

For each recommendation, the assistant will provide a short explanation. The explanation will be based on app metadata, so the user can understand why this app is suggested.

---

## Slide 4 - Planned System Flow

### Slide Content

**How It Will Work**

1. User asks a question in the App Store
2. Chat layer understands the intent
3. Search engine retrieves candidate apps
4. Ranking combines semantic, keyword, and SAREF signals
5. LLM layer prepares a short answer
6. Metadata ingestion keeps the catalogue updated

### Script

The planned flow has two main parts: the user flow and the catalogue update flow.

In the user flow, the user asks a question through the App Store assistant. The chat layer detects the intent. Then the discovery and ranking engine searches the app catalogue and returns candidate apps.

The ranking will combine semantic similarity, keyword matching, and optional SAREF signals. After that, the LLM layer will prepare a short and clear answer.

In parallel, the metadata ingestion service will collect app metadata from the official API and update the search index. This helps new or updated apps become searchable.

The delivery will be modular: a plug-in or widget for the App Store, OpenAPI-documented backend services, containerized deployment, and clear documentation.

---

## Slide 5 - Work Plan

### Slide Content

**Six-Month Plan**

- M1: setup, architecture, KPIs, API alignment
- M3: working prototype on sandbox data
- M5: integrated assistant and validation preparation
- M6: validated release, documentation, and final demo

### Script

Our project plan follows the six-month structure from the proposal.

In month one, the focus is project setup, architecture, KPI agreement, and technical alignment with the HEDGE environment.

By month three, the target is a working prototype that can process real user-style queries on the sandbox dataset.

By month five, the main components should be integrated and ready for validation. This includes the assistant flow, discovery and ranking, metadata ingestion, and the plug-in integration path.

By month six, the target is a validated release with documentation, evaluation results, and a final demonstration.

---

## Slide 6 - KPIs and Validation

### Slide Content

**Validation Targets**

- >= 70% top-2 relevance on pilot queries
- Median response time below 5 seconds
- Catalogue freshness within the agreed update window
- 50 labelled sample queries with HEDGE team
- At least 10 complete user interaction sessions

### Script

For validation, we will focus on the KPIs from the proposal.

The first main KPI is relevance. Our target is that at least 70 percent of pilot queries receive a relevant app within the first two suggestions.

The second KPI is latency. The target is a median response time below 5 seconds, measured on the agreed test setup.

The third KPI is freshness. The catalogue should be updated within the agreed update window. If webhook or event-based triggers are available later, we can align the design to support faster updates.

For evaluation, we plan to use at least 50 labelled sample queries, ideally agreed together with the HEDGE team. We also plan to record at least 10 complete user interaction sessions for validation and feedback.

---

## Slide 7 - Risks and Alignment Needs

### Slide Content

**Main Risks**

- App Store API access delay
- Response time above target
- Search quality below target
- LLM gives unsupported answers
- Integration details change

**Alignment Needed**

- Sandbox API access and metadata schema
- UI/plugin constraints
- Evaluation protocol and sample queries

### Script

We also want to be clear about risks and alignment needs.

If App Store API access is delayed, we will use a mock API and contract tests to reduce integration risk. For response time, we will use caching, local embeddings, timeouts, and fallback paths.

For search quality, we will use labelled queries and tune the ranking based on measurable results. For the LLM layer, we will keep answers short and grounded in app metadata, so the assistant does not make unsupported claims.

From the HEDGE team, the most important alignment points are sandbox API access, the metadata schema, UI and plug-in constraints, and the evaluation protocol.

Regular technical syncs will help us detect changes early and keep the project aligned with HEDGE expectations.

---

## Slide 8 - Closing

### Slide Content

**Expected Result**

HEDGE-ExpertAI will help users:

- Find relevant apps faster
- Understand why an app is recommended
- Discover apps using natural language
- Benefit from an updated catalogue

**Thank you**

### Script

To close, HEDGE-ExpertAI is focused on one clear result: making the HEDGE-IoT App Store easier to use and more helpful for users.

We want users to find relevant apps faster, understand the reason behind each recommendation, and use natural language instead of exact technical keywords.

At the same time, the project will provide a reusable technical package: a plug-in interface, OpenAPI backend, metadata ingestion, ranking, LLM-based explanations, evaluation assets, and documentation.

We believe this can support the HEDGE-IoT goal of making edge and IoT services more accessible and easier to adopt.

Thank you. I am happy to discuss questions and alignment points.

---

## Optional Short Q&A Answers

### If they ask: "Is this already connected to the real App Store?"

Recommended answer:

We are planning the integration around the official App Store API and sandbox environment. While access and final constraints are being aligned, we can work with a mock API and contract-based approach to reduce integration risk.

### If they ask: "How will you avoid LLM hallucination?"

Recommended answer:

The assistant will not answer freely from general knowledge. It will generate short explanations based on app metadata and retrieved search results. If confidence is low, the system can return a safer answer with links or app details instead of making strong claims.

### If they ask: "What do you need from us first?"

Recommended answer:

The most important first items are sandbox API access, the metadata schema, UI/plugin constraints, and agreement on the evaluation query set.

### If they ask: "Can the system support faster catalogue updates?"

Recommended answer:

Yes, the design can support periodic updates, and if webhook or event triggers are provided later, we can align the ingestion service to support faster update flows.

### If they ask: "What makes this different from normal search?"

Recommended answer:

Normal search depends mainly on exact words. HEDGE-ExpertAI will combine keyword search, semantic search, optional SAREF signals, and short explanations. So the user can describe a need, not only search with exact technical terms.

