# HEDGE-ExpertAI — Project Context

## Project Overview

**HEDGE-ExpertAI** is an AI-powered conversational assistant for the HEDGE-IoT App Store. It enables users to discover IoT applications using natural language queries and receive relevant recommendations with explainable summaries grounded in real app metadata.

Developed by **A Arti Mühendislik** as part of the HEDGE-IoT Open Call — Topic 15 (AI-Enhanced Data App Discovery & Recommendation Engine). Licensed under **Apache 2.0**.

### Architecture

The system consists of **6 microservices** + **3 infrastructure components**, all containerized via Docker Compose:

| Service | Port | Purpose |
|---|---|---|
| **gateway** | 8080→8000 | API gateway & reverse proxy |
| **chat-intent** | 8001 | Intent classification & session management |
| **expert-recommend** | 8002 | LLM-powered recommendations via Ollama |
| **discovery-ranking** | 8003 | Hybrid search engine (vector + keyword + SAREF) |
| **metadata-ingest** | 8004 | App Store metadata synchronization |
| **mock-api** | 9000 | Mock HEDGE-IoT App Store API |

**Infrastructure:**
- **Ollama** (port 11434) — hosts the Qwen3.5:2b LLM
- **Qdrant** (port 6333) — persistent vector storage
- **Redis** (port 6379) — task queue (Celery), sessions, caching

**Frontend:** React + TypeScript + Vite + Tailwind + Framer Motion validation console (port 8080 via gateway proxy).

### Data Flow

```
User → [React Validation Console] → [Gateway :8080]
                           → [Chat-Intent :8001]
                           → [Expert-Recommend :8002] → [Ollama / Qwen3.5:2b]
                           → [Discovery-Ranking :8003] → [Qdrant]
Async: [Metadata-Ingest :8004] → [App Store API] → [Discovery-Ranking] (index update)
```

## Key Technologies

| Area | Technology |
|---|---|
| Backend | Python 3.11, FastAPI, Uvicorn |
| LLM | Qwen3.5:2b via Ollama |
| Embeddings | all-MiniLM-L6-v2 (384-dim) |
| Vector DB | Qdrant v1.9.7 |
| Task Queue | Celery + Redis |
| Frontend | React 18, TypeScript, Vite, Tailwind CSS, Framer Motion |
| Containerization | Docker Compose |
| Shared Package | `hedge-shared` (Pydantic models, config, SAREF utilities) |

## Building and Running

### Prerequisites

- Docker Engine 24+ & Docker Compose v2
- ~5 GB RAM minimum (8 GB+ recommended)
- ~10 GB disk for images and models
- Linux x86_64 (tested on Ubuntu 22.04 / 24.04)

### Commands

```bash
# Setup
cp .env.example .env

# Build and start
make build
make up

# Pull the LLM model (~2.7GB)
make pull-model

# Seed the search index
make seed

# Check health
make health

# Stop
make down
```

### Makefile Targets

| Command | Description |
|---|---|
| `make build` | Build all Docker images |
| `make up` | Start all services |
| `make down` | Stop all services |
| `make logs` | View logs (follow mode) |
| `make test` | Run unit tests with coverage |
| `make test-ci` | Run tests with 80% coverage enforcement |
| `make lint` | Lint with ruff |
| `make pull-model` | Pull Qwen3.5:2b into Ollama |
| `make seed` | Trigger metadata ingestion |
| `make health` | Check health of all services |
| `make clean` | Remove containers, volumes, and images |
| `make openapi` | Export OpenAPI specs from all services |
| `make evaluate` | Run full evaluation suite |
| `make test-integration` | Run integration tests |

### Frontend

```bash
cd frontend
npm install
npm run dev      # Development server (port 5173)
npm run build    # Production build
npm run preview  # Preview production build
```

## Project Structure

```
hedge/
├── docker-compose.yml          # Full stack orchestration
├── Makefile                    # CLI commands
├── .env.example                # Environment configuration template
├── frontend/                   # React + TypeScript validation console
│   ├── src/                    # Frontend source code
│   ├── widget/                 # Embeddable widget source
│   └── package.json
├── services/
│   ├── gateway/                # API gateway (:8080 → :8000)
│   ├── chat-intent/            # Intent classification (:8001)
│   ├── expert-recommend/       # LLM recommendations (:8002)
│   ├── discovery-ranking/      # Hybrid search engine (:8003)
│   ├── metadata-ingest/        # Metadata sync (:8004)
│   └── mock-api/               # Mock App Store API (:9000)
├── shared/
│   ├── hedge_shared/           # Shared Python package
│   │   ├── config.py           # Centralized Pydantic settings
│   │   ├── models.py           # Pydantic models (AppMetadata, ChatMessage, etc.)
│   │   ├── saref.py            # SAREF ontology utilities
│   │   └── utils.py            # Common utilities
│   └── pyproject.toml          # Shared package definition
├── tests/
│   ├── unit/                   # Unit tests
│   └── integration/            # Integration tests
├── evaluation/
│   ├── evaluate.py             # Evaluation script
│   └── test_queries.json       # Test query dataset
├── docs/                       # Detailed documentation
└── scripts/                    # Utility scripts
```

## Development Conventions

- **Backend:** Python 3.11 with FastAPI. Shared code lives in `hedge-shared` package (Pydantic models + config).
- **Linting:** Uses `ruff`. Run `make lint` to check.
- **Testing:** Pytest with coverage. Unit tests in `tests/unit/`. Run `make test`. CI enforces 80% coverage on `hedge_shared`.
- **Evaluation:** Search quality metrics tracked via `evaluation/evaluate.py` with targets: Top-2 Relevance ≥ 70%, Median Latency < 5s.
- **Configuration:** All settings via environment variables (`.env` file). See `shared/hedge_shared/config.py` for the central `Settings` class.
- **SAREF Ontology:** The system leverages SAREF ontology classes as ranking signals for IoT app discovery.

## API Endpoints

The main user-facing endpoint is the chat API via the gateway:

```bash
curl -X POST http://localhost:8080/api/v1/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "I need an app for monitoring energy consumption"}'
```

Each service exposes its own REST API with auto-generated OpenAPI docs at `/docs` (FastAPI default).

## Key KPIs

| Metric | Target |
|---|---|
| Top-2 Relevance (P@2) | ≥ 70% |
| Median Response Latency | < 5 seconds |
| Catalogue Freshness | ≤ 24h update delay |
| MRR | Tracked |
| Recall@5 | Tracked |
