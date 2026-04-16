# Development Guide

Local development setup, coding standards, testing workflow, and contribution guidelines for HEDGE-ExpertAI.

---

## Table of Contents

- [Prerequisites](#prerequisites)
- [Local Development Setup](#local-development-setup)
- [Project Layout](#project-layout)
- [Running Services Locally](#running-services-locally)
- [Testing](#testing)
- [Code Style](#code-style)
- [Git Workflow](#git-workflow)
- [Adding a New Service](#adding-a-new-service)
- [Debugging](#debugging)

---

## Prerequisites

| Tool | Version | Purpose |
|---|---|---|
| Python | 3.11+ | All backend services |
| Docker | 24+ | Container builds |
| Docker Compose | v2 | Orchestration |
| pip | Latest | Package management |
| Make | Any | Build automation |
| Git | 2.x | Version control |

Optional:
- **ruff** — Python linting (`pip install ruff`)
- **pytest** — Test runner (installed with shared package deps)

---

## Local Development Setup

### 1. Clone the Repository

```bash
git clone git@github.com:RaptorBlingx/HEDGE-ExpertAI.git
cd HEDGE-ExpertAI
```

### 2. Install the Shared Package

```bash
cd shared
pip install -e ".[dev]"
cd ..
```

This installs `hedge_shared` in editable mode so changes take effect immediately.

### 3. Install Service Dependencies (for IDE support)

```bash
# Install each service's requirements for autocompletion
pip install -r services/gateway/requirements.txt
pip install -r services/chat-intent/requirements.txt
pip install -r services/expert-recommend/requirements.txt
pip install -r services/discovery-ranking/requirements.txt
pip install -r services/metadata-ingest/requirements.txt
pip install -r services/mock-api/requirements.txt
```

### 4. Configure Environment

```bash
cp .env.example .env
# Edit .env if needed
```

### 5. Start Infrastructure

```bash
# Start only infrastructure services (for local development)
docker compose up -d ollama qdrant redis
```

---

## Project Layout

```
HEDGE-ExpertAI/
├── shared/                        # Shared Python package
│   ├── pyproject.toml             # Package metadata
│   └── hedge_shared/
│       ├── __init__.py
│       ├── config.py              # Pydantic Settings (single source of truth)
│       ├── models.py              # Pydantic models
│       ├── saref.py               # SAREF ontology mapping
│       └── utils.py               # Logging, health helpers
│
├── services/
│   └── <service-name>/
│       ├── Dockerfile             # Container build
│       ├── requirements.txt       # Python dependencies
│       └── app/
│           ├── __init__.py
│           ├── main.py            # FastAPI app + health check
│           ├── routes.py          # API endpoints
│           └── ...                # Service-specific modules
│
├── frontend/                      # Embeddable widget
│   ├── index.html                 # Demo page
│   └── widget/
│       ├── hedge-expert-widget.js
│       └── hedge-expert-widget.css
│
├── evaluation/                    # Quality evaluation
│   ├── evaluate.py
│   └── test_queries.json
│
├── tests/
│   ├── unit/                      # Unit tests
│   └── integration/               # Integration tests
│
├── docs/                          # Documentation
├── scripts/                       # Utility scripts
├── docker-compose.yml
├── Makefile
├── .env.example
└── .gitignore
```

### Service Convention

Each service follows the same pattern:

```
services/<name>/
├── Dockerfile
├── requirements.txt
└── app/
    ├── __init__.py
    ├── main.py      # FastAPI app factory + health endpoint
    ├── routes.py    # API router with prefix /api/v1
    └── ...          # Domain logic modules
```

---

## Running Services Locally

### Option A: Docker Compose (recommended)

```bash
# Build and start all services
make build && make up

# Or start specific services
docker compose up -d gateway chat-intent expert-recommend

# View logs
make logs
# Or for a specific service:
docker compose logs -f gateway
```

### Option B: Direct Python (for debugging)

```bash
# Terminal 1: Start infrastructure
docker compose up -d ollama qdrant redis mock-api

# Terminal 2: Run a service directly
cd services/discovery-ranking
QDRANT_HOST=localhost QDRANT_PORT=6333 \
  uvicorn app.main:app --host 0.0.0.0 --port 8003 --reload
```

Set environment variables to point to `localhost` instead of Docker service names.

---

## Testing

### Unit Tests

```bash
# Run all unit tests
make test

# With verbose output
cd shared && python -m pytest ../tests/unit/ -v

# Run a single test file
cd shared && python -m pytest ../tests/unit/test_classifier.py -v

# Run a specific test
cd shared && python -m pytest ../tests/unit/test_classifier.py::TestClassifier::test_greeting -v
```

### Search Quality Evaluation

```bash
# Requires running services with seeded data
make up && make seed
python evaluation/evaluate.py
```

### Linting

```bash
make lint

# Or directly:
ruff check shared/ services/ tests/
```

---

## Code Style

### Python

- **Python 3.11+** — use modern syntax (`str | None`, `list[str]`)
- **Type hints** — on function signatures
- **Docstrings** — module-level and public functions
- **Logging** — use `logging.getLogger(__name__)`, not `print()`
- **Imports** — `from __future__ import annotations` at the top of each file
- **Framework** — FastAPI with Pydantic models for request/response validation
- **Async** — FastAPI supports async, but sync is used for simplicity (CPU-bound LLM)

### JavaScript

- **No framework dependencies** — vanilla JS only
- **Class names** — prefixed with `he-` for CSS isolation
- **XSS prevention** — all user input escaped via `textContent`

### Configuration

- All config via environment variables
- Defaults in `shared/hedge_shared/config.py` (single source of truth)
- Defaults must match `.env.example` and `docker-compose.yml`

---

## Git Workflow

### Branches

| Branch | Purpose |
|---|---|
| `main` | Stable release branch |
| `develop` | Active development |
| `feature/*` | New features |
| `fix/*` | Bug fixes |
| `docs/*` | Documentation changes |

### Commit Messages

Use conventional commit format:

```
feat: add SAREF boost to hybrid search
fix: handle empty query in classifier
docs: add API reference for discovery service
test: add parametrized tests for intent classifier
chore: update Docker base image to Python 3.11
```

### Remotes

The repository is mirrored on two platforms:

```bash
# GitHub (primary)
git remote add github git@github.com:RaptorBlingx/HEDGE-IoT.git

# Forgejo (mirror)
git remote add forgejo git@code.arti.ac:europe/HEDGE-IoT.git

# Push to both
git push github main
git push forgejo main
```

---

## Adding a New Service

1. Create the service directory:

```bash
mkdir -p services/new-service/app
```

2. Create `services/new-service/app/__init__.py` (empty)

3. Create `services/new-service/app/main.py`:

```python
"""New Service — FastAPI application entry point."""
from fastapi import FastAPI
from .routes import router

app = FastAPI(title="HEDGE-ExpertAI New Service", version="0.1.0")
app.include_router(router)

@app.get("/health")
def health():
    return {"status": "ok", "service": "new-service", "version": "0.1.0"}
```

4. Create `services/new-service/app/routes.py`

5. Create `services/new-service/requirements.txt`

6. Create `services/new-service/Dockerfile` (follow existing pattern)

7. Add to `docker-compose.yml`

8. Add health check URL to `services/gateway/app/routes.py` `_SERVICES`

9. Add proxy route in `services/gateway/app/routes.py` if needed

---

## Debugging

### Container Logs

```bash
# All services
make logs

# Specific service
docker compose logs -f expert-recommend

# Last 100 lines
docker compose logs --tail=100 discovery-ranking
```

### Container Shell

```bash
docker compose exec gateway /bin/bash
docker compose exec ollama /bin/bash
```

### Redis Inspection

```bash
docker compose exec redis redis-cli

# View all session keys
KEYS hedge:session:*

# Check ingestion stats
HGETALL hedge:ingest:stats

# Check a checksum
GET hedge:checksum:app-001
```

### Qdrant Inspection

```bash
# Collection info
curl http://localhost:6333/collections/hedge_apps

# Point count
curl http://localhost:6333/collections/hedge_apps/points/count
```

### Ollama

```bash
# List models
curl http://localhost:11434/api/tags

# Chat directly
curl http://localhost:11434/api/chat -d '{
  "model": "qwen3.5:2b",
  "messages": [{"role": "user", "content": "Hello"}],
  "stream": false,
  "think": false
}'
```

### Container Resources

```bash
docker stats --no-stream
```
