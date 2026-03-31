<p align="center">
  <img src="https://img.shields.io/badge/HEDGE--IoT-Open_Call_1-00897B?style=for-the-badge" alt="HEDGE-IoT Open Call 1" />
  <img src="https://img.shields.io/badge/Topic-15-blue?style=for-the-badge" alt="Topic 15" />
  <img src="https://img.shields.io/badge/License-Apache_2.0-green?style=for-the-badge" alt="License" />
  <img src="https://img.shields.io/badge/TRL-5→8-orange?style=for-the-badge" alt="TRL" />
  <img src="https://img.shields.io/badge/Python-3.11-3776AB?style=for-the-badge&logo=python&logoColor=white" alt="Python" />
  <img src="https://img.shields.io/badge/Docker-Compose-2496ED?style=for-the-badge&logo=docker&logoColor=white" alt="Docker" />
</p>

# HEDGE-IoT — ExpertAI

**Context-Aware AI Discovery and Recommendation Assistant for the HEDGE-IoT App Store**

> Developed by **A Arti Mühendislik** as part of the [HEDGE-IoT](https://hedge-iot.eu/) Open Call — Topic 15: *AI-Enhanced Data App Discovery & Recommendation Engine*

---

## What is HEDGE-ExpertAI?

HEDGE-ExpertAI is an AI-powered conversational assistant that makes the HEDGE-IoT App Store easier to explore and understand. Users ask questions in natural language and receive relevant IoT application recommendations with concise, explainable summaries grounded in real app metadata.

### Key Capabilities

| Capability | Description |
|---|---|
| **Conversational Search** | Natural language queries to discover IoT applications |
| **Hybrid Retrieval** | Combines vector similarity, keyword matching, and SAREF ontology signals |
| **Explainable Recommendations** | LLM-generated explanations grounded in real app metadata |
| **Continuous Indexing** | Automated metadata ingestion keeps the catalogue fresh (≤ 24h) |
| **Embeddable Widget** | Drop-in JavaScript plugin for the HEDGE-IoT App Store frontend |
| **SAREF Alignment** | Leverages SAREF ontology classes as ranking signals |

---

## Architecture

```
User → [Frontend Widget] → [Gateway :8080]
                               │
                         [Chat-Intent :8001]
                               │
                         [Expert-Recommend :8002] → [Ollama / Qwen3.5:2b]
                               │
                         [Discovery-Ranking :8003] → [Qdrant]

Async: [Metadata-Ingest :8004] → [App Store API / Mock API :9000]
                   │
             [Redis / Celery]
                   │
             [Discovery-Ranking] (index update)
```

**6 microservices** + **3 infrastructure components** (Ollama, Qdrant, Redis), all containerized and orchestrated with Docker Compose.

---

## Quick Start

### Prerequisites

- Docker Engine 24+ & Docker Compose v2
- ~5 GB RAM (minimum) — 8 GB+ recommended
- ~10 GB disk for images and models
- Linux x86_64 (tested on Ubuntu 22.04 / 24.04)

### Steps

```bash
# 1. Clone the repository
git clone git@github.com:RaptorBlingx/HEDGE-IoT.git
cd HEDGE-IoT/hedge-expert-ai

# 2. Configure environment
cp .env.example .env

# 3. Enable swap (recommended for 5GB servers)
sudo fallocate -l 4G /swapfile && sudo chmod 600 /swapfile
sudo mkswap /swapfile && sudo swapon /swapfile

# 4. Build and start all services
make build
make up

# 5. Pull the LLM model (~2.7GB download)
make pull-model

# 6. Seed the search index
make seed

# 7. Verify all services
make health
```

Open **http://localhost:8080** to see the chat widget, or query the API:

```bash
curl -X POST http://localhost:8080/api/v1/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "I need an app for monitoring energy consumption"}'
```

---

## Project Structure

```
HEDGE-IoT/
├── HEDGE-IoT-OC1-Proposal-HedgeExpertAI.md   # Open Call proposal document
├── hedge-expert-ai/                            # Main application
│   ├── docker-compose.yml                      # Full stack orchestration
│   ├── Makefile                                # Build, run, test commands
│   ├── .env.example                            # Environment configuration template
│   ├── shared/                                 # Shared Python package
│   │   └── hedge_shared/                       # Models, config, SAREF, utilities
│   ├── services/
│   │   ├── gateway/                            # API gateway & reverse proxy (:8080→:8000)
│   │   ├── chat-intent/                        # Intent classification & session mgmt (:8001)
│   │   ├── expert-recommend/                   # LLM-powered recommendations (:8002)
│   │   ├── discovery-ranking/                  # Hybrid search engine (:8003)
│   │   ├── metadata-ingest/                    # App Store metadata sync (:8004)
│   │   └── mock-api/                           # Mock HEDGE-IoT App Store API (:9000)
│   ├── frontend/                               # Embeddable chat widget (vanilla JS)
│   ├── evaluation/                             # Test queries & evaluation scripts
│   ├── tests/                                  # Unit & integration tests
│   ├── docs/                                   # Detailed documentation
│   └── scripts/                                # Utility scripts
└── .gitignore
```

---

## Documentation

Comprehensive documentation is available in the [`hedge-expert-ai/docs/`](hedge-expert-ai/docs/) directory:

| Document | Description |
|---|---|
| [Architecture](hedge-expert-ai/docs/architecture.md) | System design, data flows, technology choices, memory budget |
| [API Reference](hedge-expert-ai/docs/api-reference.md) | Complete REST API specification for all services |
| [Services Guide](hedge-expert-ai/docs/services-guide.md) | Deep dive into each microservice's internals |
| [Configuration Reference](hedge-expert-ai/docs/configuration-reference.md) | All environment variables with defaults and descriptions |
| [Deployment Guide](hedge-expert-ai/docs/deployment-guide.md) | Production setup, TLS, monitoring, backup, troubleshooting |
| [Plugin Integration Guide](hedge-expert-ai/docs/plugin-integration-guide.md) | Embedding the chat widget in external sites |
| [SAREF Ontology Mapping](hedge-expert-ai/docs/saref-ontology-mapping.md) | SAREF class inference and ontology alignment |
| [Evaluation & Testing](hedge-expert-ai/docs/evaluation-and-testing.md) | Search quality metrics, test framework, KPI targets |
| [Development Guide](hedge-expert-ai/docs/development-guide.md) | Local setup, coding standards, testing, contributing |

---

## KPIs & Targets

| Metric | Target | Description |
|---|---|---|
| **Top-2 Relevance (P@2)** | ≥ 70% | Fraction of top-2 results that are relevant |
| **Median Response Latency** | < 5 seconds | End-to-end query response time |
| **Catalogue Freshness** | ≤ 24h update delay | Time from app publication to searchability |
| **MRR** | Tracked | Mean Reciprocal Rank across test queries |
| **Recall@5** | Tracked | Fraction of expected apps found in top-5 |

---

## Technology Stack

| Component | Technology | Purpose |
|---|---|---|
| **LLM** | Qwen3.5:2b via Ollama | Natural language generation & explanations |
| **Embeddings** | all-MiniLM-L6-v2 | Semantic search (384-dim vectors) |
| **Vector DB** | Qdrant v1.9.7 | Persistent vector storage |
| **Task Queue** | Celery + Redis | Async ingestion, scheduling, sessions |
| **Web Framework** | FastAPI + Uvicorn | Async REST APIs with auto-docs |
| **Frontend** | Vanilla JavaScript | Zero-dependency embeddable widget |
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
make pull-model   # Pull LLM model into Ollama
make seed         # Trigger metadata ingestion
make health       # Check health of all services
make clean        # Remove containers, volumes, and images
```

---

## License

This project is licensed under the **Apache License 2.0** — see the [LICENSE](hedge-expert-ai/LICENSE) file for details.

---

## Acknowledgements

Developed by **A Arti Mühendislik** as part of the HEDGE-IoT Open Call (Topic 15).

This project has received funding from the European Union's research and innovation programmes. The HEDGE-IoT project aims to create a federated, open, and interoperable edge-computing ecosystem for IoT data services across Europe.

---

## Repository Mirrors

| Platform | URL |
|---|---|
| **GitHub** | `git@github.com:RaptorBlingx/HEDGE-IoT.git` |
| **Forgejo** | `git@code.arti.ac:europe/HEDGE-IoT.git` |
