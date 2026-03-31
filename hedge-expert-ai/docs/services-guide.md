# Services Guide

Detailed documentation for each HEDGE-ExpertAI microservice — architecture, internals, configuration, and data flow.

---

## Table of Contents

- [Service Overview](#service-overview)
- [Gateway](#gateway)
- [Chat Intent](#chat-intent)
- [Expert Recommend](#expert-recommend)
- [Discovery & Ranking](#discovery--ranking)
- [Metadata Ingest](#metadata-ingest)
- [Mock API](#mock-api)
- [Shared Package](#shared-package)
- [Infrastructure Services](#infrastructure-services)

---

## Service Overview

| Service | Port | Purpose | Dependencies |
|---|---|---|---|
| **Gateway** | 8080→8000 | API proxy, rate limiting, security headers, static files | Chat-Intent |
| **Chat-Intent** | 8001 | Intent classification, session management, routing | Redis, Expert-Recommend |
| **Expert-Recommend** | 8002 | LLM-powered recommendations & explanations | Ollama, Discovery-Ranking |
| **Discovery-Ranking** | 8003 | Hybrid search engine, vector indexing | Qdrant |
| **Metadata-Ingest** | 8004 | Periodic App Store metadata sync | Redis, Discovery-Ranking, Mock-API |
| **Mock-API** | 9000 | Development mock of HEDGE-IoT App Store | None |

### Startup Order

Docker Compose enforces health-check-based startup ordering:

```
Ollama, Qdrant, Redis (infrastructure — parallel)
       ↓
Mock-API (no dependencies)
       ↓
Discovery-Ranking (depends: Qdrant healthy)
       ↓
Metadata-Ingest (depends: Redis, Discovery-Ranking, Mock-API healthy)
Expert-Recommend (depends: Ollama, Discovery-Ranking healthy)
       ↓
Chat-Intent (depends: Redis, Expert-Recommend healthy)
       ↓
Gateway (depends: Chat-Intent healthy)
```

---

## Gateway

**Path:** `services/gateway/`

### Purpose

The Gateway is the single public-facing entry point. It:

- Proxies all client requests to internal services
- Serves the frontend widget as static files
- Applies rate limiting, security headers, and request ID tracing
- Provides an aggregated health endpoint

### Architecture

```
Client → [RateLimitMiddleware] → [RequestIDMiddleware] → [SecurityHeadersMiddleware]
              → [CORS] → [FastAPI Router] → Internal services
```

### Key Files

| File | Description |
|---|---|
| `app/main.py` | FastAPI app initialization, middleware stack, static file mounting |
| `app/routes.py` | Reverse proxy routes mapping public endpoints to internal services |
| `app/middleware.py` | Custom middleware: rate limiting, request IDs, security headers |

### Middleware Stack

Applied in order (outermost first):

1. **SecurityHeadersMiddleware** — Adds `X-Content-Type-Options`, `X-Frame-Options`, `X-XSS-Protection`, `Referrer-Policy`
2. **RequestIDMiddleware** — Injects `X-Request-ID` UUID for distributed tracing
3. **RateLimitMiddleware** — 60 requests/minute per IP (in-memory, skips `/health`)
4. **CORSMiddleware** — Configurable allowed origins (default: `*`)

### Routes

| Public Route | Internal Target | Timeout |
|---|---|---|
| `POST /api/v1/chat` | Chat-Intent `:8001` | 300s |
| `POST /api/v1/apps/search` | Discovery-Ranking `:8003` | 30s |
| `GET /api/v1/apps/{app_id}` | Discovery-Ranking `:8003` | 10s |
| `POST /api/v1/ingest/trigger` | Metadata-Ingest `:8004` | 30s |
| `GET /health` | Aggregated | 5s per service |

### Static File Serving

The Gateway serves the frontend widget from `/app/static/` inside the container (copied from `frontend/` during Docker build). Access the demo page at `http://localhost:8080/`.

### Configuration

| Variable | Default | Description |
|---|---|---|
| `CHAT_INTENT_URL` | `http://chat-intent:8001` | Chat service base URL |
| `DISCOVERY_RANKING_URL` | `http://discovery-ranking:8003` | Search service base URL |
| `METADATA_INGEST_URL` | `http://metadata-ingest:8004` | Ingest service base URL |
| `EXPERT_RECOMMEND_URL` | `http://expert-recommend:8002` | Recommend service base URL |

---

## Chat Intent

**Path:** `services/chat-intent/`

### Purpose

The Chat-Intent service handles conversational logic:

- Classifies user messages into intents (search, detail, help, greeting)
- Manages multi-turn sessions via Redis
- Routes to Expert-Recommend for search/detail intents
- Returns appropriate responses for greeting/help intents

### Intent Classification

The classifier uses keyword-based regex patterns, checked in priority order:

| Intent | Triggers | Example |
|---|---|---|
| `greeting` | `hi`, `hello`, `hey`, `good morning` | "Hello!" |
| `help` | `help`, `how do i`, `what can you do` | "How do I use this?" |
| `detail` | `tell me about`, `details of`, `app-XXX` | "Tell me about app-001" |
| `search` | `find`, `search`, `recommend`, `monitor` | "Find apps for energy" |
| `unknown` | No pattern matched (≥3 words → search) | "ok" |

Entity extraction: App IDs matching `app-\d{3}` are automatically extracted.

### Session Management

Sessions are stored in Redis with:

- **TTL:** 30 minutes (automatically refreshed on access)
- **Key format:** `hedge:session:{uuid}`
- **Data:** JSON with `messages` array and optional `context`
- **History limit:** Last 20 messages retained per session
- **Storage:** `sessionStorage` on client side (no cookies/localStorage)

### Routing Logic

```
User message → Classify intent
  ├── greeting → Static greeting response
  ├── help    → Static help response
  ├── detail  → Extract app_id → GET app from Discovery → POST explain to Expert
  ├── search  → POST recommend to Expert (LLM + search)
  └── unknown → If ≥3 words: treat as search, else: generic response
```

### Key Files

| File | Description |
|---|---|
| `app/main.py` | FastAPI app with Redis health check |
| `app/routes.py` | Chat endpoint, session endpoints, routing logic |
| `app/classifier.py` | Intent classifier with regex patterns |
| `app/session.py` | Redis-backed session CRUD with TTL |

---

## Expert Recommend

**Path:** `services/expert-recommend/`

### Purpose

The Expert-Recommend service orchestrates the recommendation pipeline:

1. Calls Discovery-Ranking for search results
2. Sends results + query to Ollama LLM for natural language explanation
3. Returns combined response

### LLM Configuration

| Parameter | Value | Notes |
|---|---|---|
| Model | Qwen3.5:2b | Lightweight, CPU-compatible |
| Temperature | 0.3 | Low creativity, high consistency |
| Max tokens | 300 | Concise responses |
| Context window | 2048 | Fits prompt + app metadata |
| Think mode | **Always false** | Qwen3.5 non-thinking mode required |
| Retry attempts | 3 | Exponential backoff (1s, 2s, 4s) |
| Timeout | 180s | CPU inference with swap |

### Prompt System

The LLM uses a carefully crafted prompt system:

**System prompt** constrains the model to:
- Only use information from provided metadata
- Be concise (2-3 sentences per app)
- Not invent features not in the metadata
- Honest when no apps match well

**Recommendation template** includes:
- User query
- Formatted app context (title, description, tags, SAREF, inputs, outputs, score)
- Instructions for summarizing matches

**Explanation template** for single-app detail:
- User query
- Full app metadata
- Instructions for relevance explanation

### Safety Measures

- `<think>` tags are stripped from responses (Qwen3.5 safety)
- Responses are grounded in source metadata only
- Failed LLM calls fall back to "Here are the most relevant apps" text

### Key Files

| File | Description |
|---|---|
| `app/main.py` | FastAPI app with Ollama health check |
| `app/routes.py` | `/recommend` and `/explain` endpoints |
| `app/recommender.py` | Pipeline orchestrator: search → LLM explain |
| `app/llm_client.py` | Ollama API client with retry logic |
| `app/prompts.py` | System prompt, templates, context formatting |

---

## Discovery & Ranking

**Path:** `services/discovery-ranking/`

### Purpose

The hybrid search engine:

- Indexes app metadata as 384-dimensional vectors in Qdrant
- Performs hybrid search combining vector similarity, keyword matching, and SAREF ontology boosting
- Manages the vector collection lifecycle

### Hybrid Search Algorithm

The search pipeline:

1. **Embed query** using `all-MiniLM-L6-v2` (384-dim, normalized)
2. **Vector search** in Qdrant — retrieve `top_k × 3` candidates (max 50)
3. **Keyword scoring** — BM25-lite: fraction of query tokens found in document
4. **SAREF boost** — +1.0 if app's `saref_type` matches the query's SAREF class
5. **Score fusion:** `0.6 × vector + 0.3 × keyword + 0.1 × saref`
6. **Re-rank** and return top-k results

### Embedding Model

| Property | Value |
|---|---|
| Model | `all-MiniLM-L6-v2` |
| Dimensions | 384 |
| Size | ~80 MB |
| Loading | Lazy singleton (first request) |
| CPU-only | Yes (no GPU required) |
| Normalization | Enabled |

### Qdrant Configuration

| Property | Value |
|---|---|
| Collection | `hedge_apps` |
| Distance metric | Cosine |
| Vector size | 384 |
| Memory limit | 256 MB |
| Compatibility check | Disabled (`check_compatibility=False`) |

### Index Text Construction

For each app, the following fields are concatenated for embedding:

```
{title} {description} {tags joined by spaces}
```

### App ID Hashing

App IDs (e.g., `app-001`) are converted to integer point IDs using SHA-256:

```python
int(hashlib.sha256(app_id.encode()).hexdigest()[:15], 16)
```

### Key Files

| File | Description |
|---|---|
| `app/main.py` | FastAPI app with Qdrant connection at startup |
| `app/routes.py` | Search, index, and app-detail endpoints |
| `app/embeddings.py` | Sentence-transformer model singleton |
| `app/indexer.py` | Qdrant CRUD: upsert, delete, retrieve, collection management |
| `app/searcher.py` | Hybrid search algorithm with score fusion |

---

## Metadata Ingest

**Path:** `services/metadata-ingest/`

### Purpose

Automated pipeline for keeping the search index synchronized with the App Store:

- Periodically fetches all apps from the App Store API
- Detects changes via SHA-256 checksums stored in Redis
- Sends new/updated apps to Discovery-Ranking for indexing
- Tracks ingestion statistics

### Celery Configuration

| Property | Value |
|---|---|
| Broker | Redis |
| Backend | Redis |
| Schedule | Every 7200s (2 hours) by default |
| Concurrency | 1 worker |
| Max tasks per child | 50 (prevents memory leaks) |
| Prefetch multiplier | 1 (one task at a time) |
| Max retries | 2 |
| Retry countdown | 60s (fetch fail), 30s (index fail) |

### Ingestion Flow

```
Celery Beat → ingest_all task
    ├── Fetch all apps from API (paginated)
    ├── For each app:
    │     ├── Compute SHA-256 checksum
    │     ├── Compare with stored checksum in Redis
    │     ├── If changed → add to batch
    │     └── Update checksum in Redis
    ├── Batch POST to Discovery-Ranking /api/v1/apps/index
    └── Update stats in Redis (hedge:ingest:stats)
```

### Redis Keys

| Key | Purpose |
|---|---|
| `hedge:checksum:{app_id}` | SHA-256 checksum for change detection |
| `hedge:ingest:last_run` | ISO timestamp of last run |
| `hedge:ingest:stats` | Hash with `total_fetched`, `new`, `updated`, `unchanged` |

### App Store Client

The service uses an adapter pattern with two implementations:

| Client | Usage |
|---|---|
| `MockApiClient` | Fetches from the mock API (development) |
| `HedgeApiClient` | Placeholder for the real HEDGE-IoT API (production) |

The factory function `get_client()` selects the client based on `HEDGE_API_URL`:
- If `HEDGE_API_URL` is set → use `HedgeApiClient`
- Otherwise → use `MockApiClient` with `MOCK_API_URL`

### Key Files

| File | Description |
|---|---|
| `app/main.py` | FastAPI app with Redis health check |
| `app/routes.py` | Manual trigger and status endpoints |
| `app/celery_app.py` | Celery configuration with beat schedule |
| `app/client.py` | App Store API client adapter (mock + real) |
| `app/tasks/ingest.py` | Celery task: fetch, diff, index pipeline |

---

## Mock API

**Path:** `services/mock-api/`

### Purpose

A development-only mock of the HEDGE-IoT App Store API. Ships with **50 seed applications** covering 8 SAREF categories.

### Data

The seed data is in `app/data/apps.json` — a JSON array of 50 app objects with:

| Field | Type | Description |
|---|---|---|
| `id` | `string` | Unique ID (`app-001` through `app-050`) |
| `title` | `string` | Application name |
| `description` | `string` | Detailed description |
| `tags` | `string[]` | Keyword tags |
| `saref_type` | `string` | SAREF ontology class |
| `input_datasets` | `string[]` | Required data inputs |
| `output_datasets` | `string[]` | Generated data outputs |
| `version` | `string` | Semantic version |
| `publisher` | `string` | Publisher organization |
| `created_at` | `string` | ISO 8601 creation date |
| `updated_at` | `string` | ISO 8601 last update |

### SAREF Category Distribution

| Category | Count | Example Apps |
|---|---|---|
| Energy | ~7 | SmartEnergy Monitor, Solar Panel Optimizer |
| Building | ~7 | BuildingComfort Pro, Smart Lighting |
| Environment | ~6 | AirSense, Flood Warning System |
| Agriculture | ~6 | SmartIrrigation, Crop Health Analyzer |
| Water | ~6 | Leak Detection, Water Quality Monitor |
| City | ~6 | Traffic Optimizer, Smart Parking |
| Health | ~6 | Patient Monitor, Fall Detection |
| Manufacturing | ~6 | Predictive Maintenance, Quality Inspection |

---

## Shared Package

**Path:** `shared/hedge_shared/`

A Python package installed in all services providing common types and utilities.

### Modules

| Module | Purpose |
|---|---|
| `config.py` | Centralized `Settings` class via Pydantic Settings — single source of truth for defaults |
| `models.py` | Pydantic models: `AppMetadata`, `SearchQuery`, `SearchResult`, `ChatRequest`, `ChatResponse`, etc. |
| `saref.py` | SAREF ontology keyword-to-class mapping with inference functions |
| `utils.py` | Logging setup and health check response builder |

### Installation

The package is installed in each Docker image via:

```dockerfile
COPY shared/ /shared/
RUN pip install --no-cache-dir /shared/
```

For local development:

```bash
cd shared && pip install -e .
```

---

## Infrastructure Services

### Ollama

| Property | Value |
|---|---|
| Image | `ollama/ollama:latest` |
| Port | 11434 |
| Memory limit | 5500 MB (+3000 MB swap) |
| Model | Qwen3.5:2b (~2.7 GB download) |
| Purpose | LLM inference for explanations |

### Qdrant

| Property | Value |
|---|---|
| Image | `qdrant/qdrant:v1.9.7` |
| Ports | 6333 (REST), 6334 (gRPC) |
| Memory limit | 256 MB |
| Purpose | Vector storage for app embeddings |

### Redis

| Property | Value |
|---|---|
| Image | `redis:7-alpine` |
| Port | 6379 |
| Memory limit | 64 MB |
| Max memory policy | `allkeys-lru` |
| Purpose | Celery broker, session store, checksum cache |
