# Changelog

All notable changes to HEDGE-ExpertAI will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- Strict `/api/v2` metadata, search, dialogue, SSE, event, catalogue and JSON-LD contracts.
- PostgreSQL authority for catalogue revisions, transactional indexing outbox, ingestion runs/quarantine, corpus manifests and verified recommendation events.
- Deterministic 120-app synthetic `AppMetadataV2` catalogue with eight locales and ten records for each of twelve SAREF extensions.
- URI-level SAREF annotation registry, provenance/review fields and JSON-LD export.
- Independent PostgreSQL full-text and Qdrant dense retrieval with weighted reciprocal-rank fusion and typed filters.
- Eight-language Rasa NLU corpus with 25 examples per intent/language; deterministic application-owned dialogue state and follow-ups.
- Production configuration validator, hardening Compose overlay, non-root images, readiness semantics and distributed Valkey rate limits.
- Proposal traceability matrix, provisional Store adapter contract, corpus manifest and honest v2 evaluation evidence register.
- Deterministic Docker end-to-end acceptance profile covering real multilingual Rasa NLU, transactional ingestion, localized filtered retrieval, and versioned grounded SSE without requiring Ollama.
- Frontend component tests plus CI secret-history scanning, SPDX SBOM generation, and high-severity dependency scanning.
- Advisory-locked database migrations, scheduled 30-day event aggregation/erasure, encrypted three-store backups, and disposable restore drills.
- Machine-enforced Python licence denial and a reviewed exact npm licence allowlist with retained CI inventories.

### Changed
- PostgreSQL is authoritative; Qdrant is a versioned rebuildable index promoted through an alias.
- Redis is replaced by separate Valkey cache/session/rate-limit and AOF queue services.
- Embeddings use pinned `intfloat/multilingual-e5-small` with required E5 prefixes.
- Streaming emits real server stages and early recommendations; generated explanation text is validated before emission and hidden-reasoning tags are suppressed.
- Widget and validation console use v2 locale, feedback, app-open, cancellation and session-deletion flows.
- Backend runtime dependencies now install from hash-verified locks; direct container images and GitHub Actions are pinned by immutable digest or commit.
- CI enforces zero Ruff findings, 80% core branch coverage, OpenAPI drift, generated catalogue/NLU/evaluation drift, dependency audits, frontend tests, and the live deterministic stack gate.

### Removed
- Incomplete 75-record demo catalogue, fabricated client-side “thinking” stages and browser query-string API-key support.

### Security
- Added fail-closed production defaults, trusted-proxy parsing, OIDC role boundaries, privacy-minimized metrics/logging and idempotent verified events.
- Upgraded FastAPI/Starlette and PyJWT to audited pinned versions; all seven Python runtime locks and the npm production/development graph currently report no known vulnerabilities.

## [0.4.0] — 2026-04-15

### Added
- **Evaluation metrics** — NDCG@5, MAP (Mean Average Precision), 95% bootstrap
  confidence intervals for P@2 and MRR, per-SAREF-category breakdown, and app
  exposure rate in search mode
- **Session recording** — new event logging system (`log_session_event`) records
  timestamped start/message/recommendation/feedback events; new endpoints
  `GET /api/v1/sessions/recorded` and `GET /api/v1/sessions/recorded/{id}` for
  Objective 5 validation (≥ 10 complete user-interaction sessions)
- **SAREF entity extraction** — classifier now extracts SAREF class entities from
  queries (8 domains: Energy, Building, Environment, Water, Agriculture, City,
  Health, Manufacturing) in addition to app ID entities
- **BM25 with TF saturation** — keyword scoring upgraded from simple token
  fraction to BM25-inspired scoring with k1/b parameters and term frequency
  normalization
- **Multilingual stopwords** — search tokenizer now filters stopwords in 7
  European languages (EN, DE, FR, ES, IT, NL, PT)
- **Prometheus metrics** — all services now expose `/metrics` endpoint with
  request counters, latency summaries, and error counts in Prometheus text format
  via shared `MetricsMiddleware`
- **Security headers** — gateway adds Content-Security-Policy, Permissions-Policy,
  and optional HSTS (`ENABLE_HSTS=true`) headers
- **Security roadmap** — new `docs/security-roadmap.md` documenting current state
  and phased plan for TLS, RBAC, OAuth, key rotation, and log anonymization

### Changed
- Classifier module now includes RASA design-decision documentation explaining
  why regex is sufficient for OC1 scope; additional search patterns for domain
  keywords and intent verbs
- `_keyword_score` in searcher uses BM25 k1=1.2, b=0.75 saturation instead of
  raw token fraction

## [0.3.0] — 2026-04-15

### Added
- **Feedback UI** — thumbs-up/down buttons on every recommendation in both React
  frontend (`App.tsx`) and embeddable widget (`hedge-expert-widget.js`); submits
  accept/dismiss actions to `/api/v1/feedback` for KPI tracking
- **Celery beat reliability** — metadata-ingest container now uses `supervisord`
  to manage both Celery worker+beat and Uvicorn; either process is auto-restarted
  on crash (replaces fragile `&` background shell pattern)
- **Celery health monitoring** — `/health` endpoint on metadata-ingest now checks
  `hedge:ingest:last_run` timestamp; reports `degraded` if Celery beat appears
  stale (configurable via `CELERY_STALE_SECONDS`, default 6 h)
- **CI/CD coverage enforcement** — GitHub Actions workflow now installs all
  service dependencies, runs unit tests with `--cov-fail-under=80`, and triggers
  on `develop` branch pushes
- **Evaluation improvements** — feedback stats always reported (no longer
  requires `--report-feedback`); chat results now show E2E latency with KPI
  target check; app exposure rate computes against 75 apps; acceptance rate
  computed from accept/(accept+dismiss)

### Changed
- D3.1 Evaluation Report updated to v1.2: consistent 75-app / 69-query numbers
  throughout; added E2E latency note distinguishing search vs chat latency;
  added pending KPI rows for acceptance rate and explanation accuracy
- `--total-apps` default in `evaluate.py` changed from 50 to 75

### Fixed
- D3.1 report inconsistency where body referenced 50 apps / 53 queries while
  v1.1 note mentioned 75 apps / 69 queries

## [0.2.0] — 2025-06-06

### Added
- Stopword removal in hybrid search queries (~175 English + domain-neutral stopwords)
- Score threshold filter (0.30) eliminates low-confidence search results
- Real SSE streaming in React frontend (`App.tsx`) — replaces fake word-by-word reveal
- Real SSE streaming in embeddable widget (`hedge-expert-widget.js`)
- Multi-mode evaluation framework (`--mode search|chat|stream|all`)
- Chat evaluation with end-to-end latency, P@2, explanation quality, and app exposure metrics
- Stream evaluation with TTFT, Time-to-First-App, and total duration via SSE parsing
- Feedback stats reporting in evaluation script (`--report-feedback`)
- Unit tests for `searcher.py` (23 tests), `llm_client.py` (11 tests), `recommender.py` (19 tests)
- 25 new mock apps (app-051 through app-075) — total 75 apps across 10 SAREF categories
- Edge-case test queries: vague, typo, multi-domain, empty SAREF, minimal fields (16 new queries)
- Makefile targets: `evaluate`, `evaluate-search`, `evaluate-chat`, `evaluate-stream`, `test-integration`
- 7-day TTL on Redis checksum keys to auto-expire stale ingestion data

### Changed
- Docker memory limits tuned for 5GB RAM: Ollama 4096m, discovery-ranking 384m, chat-intent/expert-recommend 128m
- `AppMetadata.saref_class` now accepts `saref_type` alias via Pydantic `Field(alias="saref_type")`
- `.env.example` version bumped to 0.2.0

## [0.1.0] — 2026-03-15

### Added
- Initial project structure and shared package (`hedge_shared`)
- Mock HEDGE-IoT App Store API with 46 seed applications across 8 SAREF categories
- Discovery & ranking engine with hybrid search (0.6×vector + 0.3×keyword + 0.1×SAREF boost)
- Metadata ingestion pipeline with Celery scheduled tasks and SHA-256 change detection
- Expert recommendation service with Qwen3.5:2b via Ollama
- Chat & intent service with keyword-based intent classifier and Redis session management
- API gateway with rate limiting (60 req/min), security headers, and request ID tracing
- Embeddable frontend chat widget (vanilla JS, zero dependencies)
- React validation console with dual-pane layout (catalog browser + chat interface)
- SAREF ontology mapping with 8 classes and 150+ domain keywords
- Evaluation framework with 50 labelled test queries and IR metrics (P@2, Recall@5, MRR)
- Docker Compose deployment with memory-bounded containers (5 GB total)
- CI/CD pipeline with GitHub Actions (lint → test → build)
- Comprehensive documentation suite (9 guides + proposal)
- Apache 2.0 open-source licence

## [0.0.1] — 2026-01-20

### Added
- Repository initialisation and project scaffolding
- Shared Pydantic models and configuration module
- Docker Compose skeleton with Ollama, Qdrant, and Redis infrastructure
- `.env.example` configuration template
- README with project overview and quick-start instructions
