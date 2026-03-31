# Changelog

All notable changes to HEDGE-ExpertAI will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- Initial project structure and shared package
- Mock HEDGE-IoT App Store API with 50 seed applications
- Discovery & ranking engine with hybrid search (vector + keyword + SAREF boost)
- Metadata ingestion pipeline with Celery scheduled tasks
- Expert recommendation service with Qwen3.5:2b via Ollama
- Chat & intent service with keyword-based intent classifier
- API gateway with CORS, rate limiting, and security headers
- Embeddable frontend chat widget (vanilla JS)
- Evaluation framework with 50+ labelled test queries
- Docker Compose deployment with memory-bounded containers
- OpenAPI specification for all service endpoints
- CI/CD pipeline with GitHub Actions
