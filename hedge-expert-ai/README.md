# HEDGE-ExpertAI

**Context-Aware AI Discovery and Recommendation Assistant for the HEDGE-IoT App Store**

[![License](https://img.shields.io/badge/License-Apache_2.0-blue.svg)](LICENSE)

## Overview

HEDGE-ExpertAI is an AI-powered assistant that makes the HEDGE-IoT App Store easier to explore and understand. It provides:

- **Conversational search** — ask questions in natural language to find relevant IoT applications
- **Hybrid retrieval** — combines keyword matching, vector similarity, and SAREF ontology signals
- **Explainable recommendations** — LLM-generated explanations grounded in real app metadata
- **Continuous indexing** — automatically discovers and indexes new apps from the App Store API
- **Embeddable widget** — drop-in JavaScript plugin for the HEDGE-IoT App Store frontend

## Architecture

```
User → [Frontend Widget] → [Gateway :8000]
                              ↓
                        [Chat-Intent :8001]
                              ↓
                        [Expert-Recommend :8002] → [Ollama / Qwen3.5:2b]
                              ↓
                        [Discovery-Ranking :8003] → [Qdrant]

Async: [Metadata-Ingest :8004] → [App Store API]
                   ↓
             [Redis] (Celery)
                   ↓
             [Discovery-Ranking] (index update)
```

## Quick Start

### Prerequisites

- Docker & Docker Compose v2+
- ~5 GB RAM available (minimum)
- ~10 GB disk for images and models

### 1. Clone and configure

```bash
git clone <repo-url> hedge-expert-ai
cd hedge-expert-ai
cp .env.example .env
```

### 2. Build and start

```bash
make build
make up
```

### 3. Pull the LLM model

```bash
make pull-model
```

### 4. Seed the search index

```bash
make seed
```

### 5. Verify

```bash
make health
```

### 6. Try it

Open `http://localhost:8000` in your browser to see the chat widget, or query the API directly:

```bash
curl -X POST http://localhost:8000/api/v1/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "I need an app for monitoring energy consumption"}'
```

## Project Structure

```
hedge-expert-ai/
├── shared/              # Shared Python package (models, config, SAREF)
├── services/
│   ├── gateway/         # API gateway & reverse proxy
│   ├── chat-intent/     # Intent classification & session management
│   ├── expert-recommend/# LLM-powered recommendations
│   ├── discovery-ranking/# Hybrid search engine
│   ├── metadata-ingest/ # App Store metadata sync
│   └── mock-api/        # Mock HEDGE-IoT App Store API
├── frontend/            # Embeddable chat widget
├── evaluation/          # Test queries & evaluation scripts
├── tests/               # Unit & integration tests
├── docs/                # Architecture, deployment, plugin guides
└── scripts/             # Utility scripts
```

## Documentation

| Document | Description |
|---|---|
| [Architecture](docs/architecture.md) | System design, data flows, technology choices, memory budget |
| [API Reference](docs/api-reference.md) | Complete REST API specification for all services |
| [Services Guide](docs/services-guide.md) | Deep dive into each microservice's internals |
| [Configuration Reference](docs/configuration-reference.md) | All environment variables with defaults and descriptions |
| [Deployment Guide](docs/deployment-guide.md) | Production setup, TLS, monitoring, backup, troubleshooting |
| [Plugin Integration Guide](docs/plugin-integration-guide.md) | Embedding the chat widget in external sites |
| [SAREF Ontology Mapping](docs/saref-ontology-mapping.md) | SAREF class inference and ontology alignment |
| [Evaluation & Testing](docs/evaluation-and-testing.md) | Search quality metrics, test framework, KPI targets |
| [Development Guide](docs/development-guide.md) | Local setup, coding standards, testing, contributing |

## Configuration

All configuration is via environment variables. See [.env.example](.env.example) for the full list with defaults, or the [Configuration Reference](docs/configuration-reference.md) for detailed documentation.

Key settings:
| Variable | Default | Description |
|----------|---------|-------------|
| `OLLAMA_MODEL` | `qwen3.5:2b` | LLM model name in Ollama |
| `EMBEDDING_MODEL` | `all-MiniLM-L6-v2` | Sentence embedding model |
| `INGEST_INTERVAL_SECONDS` | `7200` | Metadata sync interval (2h) |
| `RASA_ENABLED` | `false` | Enable RASA intent classifier |
| `RERANKER_ENABLED` | `false` | Enable cross-encoder reranker |

## KPIs

| Metric | Target |
|--------|--------|
| Top-2 relevance (P@2) | ≥ 70% |
| Median response latency | < 5 seconds |
| Catalogue freshness | ≤ 24h update delay |

See [Evaluation & Testing](docs/evaluation-and-testing.md) for details on metrics and testing.

## License

Apache-2.0 — see [LICENSE](LICENSE).

## Acknowledgements

Developed by A Arti Mühendislik as part of the HEDGE-IoT Open Call (Topic 15).

## Repository Mirrors

| Platform | URL |
|---|---|
| **GitHub** | `git@github.com:RaptorBlingx/HEDGE-IoT.git` |
| **Forgejo** | `git@code.arti.ac:europe/HEDGE-IoT.git` |
