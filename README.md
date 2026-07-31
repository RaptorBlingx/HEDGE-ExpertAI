<p align="center">
  <img src="https://img.shields.io/badge/HEDGE--IoT-Open_Call_1-00897B?style=for-the-badge" alt="HEDGE-IoT Open Call 1" />
  <img src="https://img.shields.io/badge/Topic-15-blue?style=for-the-badge" alt="Topic 15" />
  <img src="https://img.shields.io/badge/License-Apache_2.0-green?style=for-the-badge" alt="License" />
  <img src="https://img.shields.io/badge/Status-Production_Hardening-orange?style=for-the-badge" alt="Production hardening status" />
  <img src="https://img.shields.io/badge/Python-3.11-3776AB?style=for-the-badge&logo=python&logoColor=white" alt="Python" />
  <img src="https://img.shields.io/badge/Docker-Compose-2496ED?style=for-the-badge&logo=docker&logoColor=white" alt="Docker" />
</p>

# HEDGE-ExpertAI

**Context-Aware AI Discovery and Recommendation Assistant for the HEDGE-IoT App Store**

> Developed by **A Arti Mühendislik** as part of the [HEDGE-IoT](https://hedge-iot.eu/) Open Call — Topic 15: *AI-Enhanced Data App Discovery & Recommendation Engine*

> **Release status:** active production-hardening work. The v2 design is implemented in this branch, but the project must not be described as production-ready and proposal KPIs must not be marked passed until the Release 3 acceptance evidence in the [traceability matrix](docs/traceability-matrix.md) is retained and reviewed. The real HEDGE Store API is intentionally not connected; only its versioned adapter boundary is present.

---

## What is HEDGE-ExpertAI?

HEDGE-ExpertAI is an AI-powered conversational assistant intended to make the HEDGE-IoT App Store easier to explore and understand. Users ask questions in natural language and receive catalogue recommendations with evidence-linked summaries. Until the real Store API is available, the repository uses clearly labelled synthetic metadata.

### Key Capabilities

| Capability | Description |
|---|---|
| **Conversational Search** | Natural language queries to discover IoT applications |
| **Hybrid Retrieval** | Combines vector similarity, keyword matching, and SAREF ontology signals |
| **Explainable Recommendations** | LLM-generated explanations grounded in real app metadata |
| **Replay-safe Indexing** | PostgreSQL revisions and an outbox make indexing retryable; freshness is a target, not yet a measured claim |
| **Embeddable Widget** | Production delivery artifact for App Store integration |
| **Validation Console** | React-based internal tool for development and evaluation |
| **SAREF Alignment** | Leverages SAREF ontology classes as ranking signals |

---

## Architecture

```
User → [Embeddable Widget / Dev Console] → [Gateway :8080]
                               │
                         [Chat-Intent :8001]
                               │
                         [Expert-Recommend :8002] → [Ollama / Qwen3.5:2b]
                               │
                         [Discovery-Ranking :8003] → [PostgreSQL + Qdrant]

Async: [Metadata-Ingest :8004] → [App Store API / Mock API :9000]
                   │
             [Valkey Queue / Celery]
                   │
             [Discovery-Ranking] (index update)
```

PostgreSQL is authoritative, Qdrant is a rebuildable derived index, and separate Valkey instances hold bounded operational state and the persistent queue.

---

## Quick Start

### Prerequisites

- Docker Engine 24+ & Docker Compose v2
- 8 GB RAM minimum — 16 GB recommended with Rasa and local generation together
- ~20 GB disk plus space for backups, snapshots, and retained logs
- Linux x86_64 (tested on Ubuntu 22.04 / 24.04)

### Steps

```bash
# 1. Clone the repository
git clone git@github.com:RaptorBlingx/HEDGE-ExpertAI.git
cd HEDGE-ExpertAI

# 2. Configure environment
cp .env.example .env

# 3. Build and start all services
make build
make up

# 4. Pull the pinned deployment model
make pull-model

# 5. Seed the authoritative catalogue and derived index
make seed

# 6. Verify all services
make health
```

Open **http://localhost:8080/demo.html** to validate the production widget delivery, or **http://localhost:8080** to access the internal validation console. You can also query the API directly:

```bash
curl -X POST http://localhost:8080/api/v2/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "I need an app for monitoring energy consumption", "locale": "en", "filters": {}}'
```

---

## Project Structure

```
HEDGE-ExpertAI/
├── .github/                                    # CI workflow configuration
├── .env.example                                # Environment configuration template
├── CHANGELOG.md
├── LICENSE
├── Makefile                                    # Build, run, test commands
├── docker-compose.yml                          # Full stack orchestration
├── docs/                                       # Detailed documentation
│   └── proposals/
│       └── HEDGE-IoT-OC1-Proposal-HedgeExpertAI.md
├── evaluation/                                 # Test queries & evaluation scripts
├── frontend/
│   ├── src/                                    # React + TypeScript validation console (dev only)
│   └── widget/                                 # Production widget assets + demo host page
├── scripts/                                    # Utility scripts
├── services/
│   ├── gateway/                                # API gateway & reverse proxy (:8080 -> :8000)
│   ├── chat-intent/                            # Intent classification & session mgmt (:8001)
│   ├── expert-recommend/                       # LLM-powered recommendations (:8002)
│   ├── discovery-ranking/                      # Hybrid search engine (:8003)
│   ├── metadata-ingest/                        # App Store metadata sync (:8004)
│   └── mock-api/                               # Mock HEDGE-IoT App Store API (:9000)
├── shared/                                     # Shared Python package
│   └── hedge_shared/                           # Models, config, SAREF, utilities
└── tests/                                      # Unit & integration tests
```

---

## Documentation

Comprehensive documentation is available in the [`docs/`](docs/) directory:

| Document | Description |
|---|---|
| [Architecture](docs/architecture.md) | System design, data flows, technology choices, memory budget |
| [API Reference](docs/api-reference.md) | Complete REST API specification for all services |
| [Services Guide](docs/services-guide.md) | Deep dive into each microservice's internals |
| [Configuration Reference](docs/configuration-reference.md) | All environment variables with defaults and descriptions |
| [Deployment Guide](docs/deployment-guide.md) | Production setup, TLS, monitoring, backup, troubleshooting |
| [Plugin Integration Guide](docs/plugin-integration-guide.md) | Embedding the production widget in external sites |
| [Widget Quick Start](docs/widget-quick-start.md) | Fast path for deploying and testing the production widget |
| [SAREF Ontology Mapping](docs/saref-ontology-mapping.md) | SAREF class inference and ontology alignment |
| [Evaluation & Testing](docs/evaluation-and-testing.md) | Search quality metrics, test framework, KPI targets |
| [Local Acceptance Evidence](docs/evidence/2026-07-31-local-acceptance.md) | Reproducible local gate results and explicit evidence limitations |
| [Development Guide](docs/development-guide.md) | Local setup, coding standards, testing, contributing |

---

## KPIs & Targets

| Metric | Target | Description |
|---|---|---|
| **HitRate@2** | ≥ 70% | Primary target; pending review of the new held-out labels |
| **Average first useful recommendation** | < 5 seconds | Pending target-node load evidence; TTFT and completion are reported separately |
| **Catalogue Freshness** | ≤ 2h operational / ≤ 24h outer | Pending authoritative revision-to-searchable evidence |
| **MRR** | Tracked | Mean Reciprocal Rank across test queries |
| **Recall@5** | Tracked | Fraction of expected apps found in top-5 |

---

## Technology Stack

| Component | Technology | Purpose |
|---|---|---|
| **LLM** | Qwen3.5:2b via Ollama | Natural language generation & explanations |
| **Embeddings** | multilingual-e5-small, audited revision | Multilingual semantic search with required query/passage prefixes |
| **Vector DB** | Qdrant 1.18.2 | Versioned, rebuildable derived index |
| **Durable Store** | PostgreSQL 16.9 | Catalogue revisions, outbox, corpus and verified events |
| **Operational State** | Celery + separate Valkey cache/queue | Async ingestion, bounded sessions, cache and distributed rate limits |
| **Web Framework** | FastAPI + Uvicorn | Async REST APIs with auto-docs |
| **Frontend** | Widget + React + TypeScript + Vite + Tailwind + Framer Motion | Production embeddable widget plus internal validation console |
| **Containerization** | Docker Compose | Single-command deployment |
| **Language** | Python 3.11 | All backend services |

---

## Make Commands

```bash
make build        # Build all Docker images
make up           # Start all services
make down         # Stop all services
make logs         # View logs (follow mode)
make test         # Run unit tests
make lint         # Lint with ruff
make frontend-test # Run the pinned frontend component tests
make migrate      # Apply ordered PostgreSQL migrations once
make e2e          # Run deterministic live-stack acceptance
make backup       # Encrypted backup; requires BACKUP_* file/path variables
make restore-drill BACKUP_SET=/absolute/path # Validate isolated recovery
make pull-model   # Pull LLM model into Ollama
make seed         # Trigger metadata ingestion
make health       # Check health of all services
make clean        # Destructive local reset; inspect the Make target before use
```

---

## License

This project is licensed under the **Apache License 2.0** — see the [LICENSE](LICENSE) file for details.

---

## Acknowledgements

Developed by **A Arti Mühendislik** as part of the HEDGE-IoT Open Call (Topic 15).

This project has received funding from the European Union's research and innovation programmes. The HEDGE-IoT project aims to create a federated, open, and interoperable edge-computing ecosystem for IoT data services across Europe.
