# Changelog

All notable changes to HEDGE-ExpertAI will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

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
