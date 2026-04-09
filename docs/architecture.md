# HEDGE-ExpertAI Architecture

## System Overview

HEDGE-ExpertAI is a microservice-based AI assistant for the HEDGE-IoT App Store. It provides conversational discovery and recommendation of IoT applications using hybrid search and LLM-powered explanations.

## Service Architecture

```
┌─────────────────┐     ┌───────────────────┐
│  Frontend Widget │────▶│  Gateway :8000     │
│  (Vanilla JS)   │     │  (FastAPI proxy)   │
└─────────────────┘     └───────┬───────────┘
                                │
                 ┌──────────────┼──────────────┐
                 ▼              ▼              ▼
        ┌────────────┐  ┌────────────┐  ┌──────────────┐
        │ Chat-Intent│  │  Discovery │  │ Metadata     │
        │ :8001      │  │  Ranking   │  │ Ingest :8004 │
        │            │  │  :8003     │  │              │
        └─────┬──────┘  └─────┬──────┘  └──────┬───────┘
              │               │                 │
              ▼               ▼                 ▼
        ┌────────────┐  ┌──────────┐     ┌──────────┐
        │  Expert    │  │  Qdrant  │     │  Redis   │
        │  Recommend │  │  :6333   │     │  :6379   │
        │  :8002     │  └──────────┘     └──────────┘
        └─────┬──────┘
              │
              ▼
        ┌──────────┐
        │  Ollama  │
        │  :11434  │
        │ qwen3.5:2b │
        └──────────┘
```

## Data Flow

### Chat Flow
1. User sends message → **Gateway** (rate limiting, CORS, security headers)
2. Gateway proxies to **Chat-Intent** (intent classification, session management)
3. Chat-Intent classifies intent (search/detail/help/greeting)
4. For search: calls **Expert-Recommend** → which calls **Discovery-Ranking** for search results → then **Ollama** for LLM explanation
5. Response flows back through the chain with app recommendations + natural language explanation

### Ingestion Flow
1. **Celery Beat** triggers periodic ingestion (every 2 hours)
2. **Metadata-Ingest** fetches apps from App Store API (mock or real)
3. Checksums compared against Redis cache for change detection
4. New/updated apps sent to **Discovery-Ranking** for vector indexing
5. **Discovery-Ranking** embeds text with MiniLM → upserts to **Qdrant**

### Search Flow
1. Query text embedded using **all-MiniLM-L6-v2** (384-dim vectors)
2. Stopword removal on query tokens (~175 English + domain-neutral stopwords)
3. Vector search in **Qdrant** retrieves candidates (top_k × 3)
4. Keyword scoring applied (BM25-lite: token overlap ratio)
5. SAREF ontology boost for matching categories (+0.1)
6. Combined score: `0.6 × vector + 0.3 × keyword + 0.1 × saref`
7. Score threshold filter (≥ 0.30) eliminates low-confidence results
8. Top-k results returned with metadata

## Technology Choices

| Component | Technology | Rationale |
|-----------|-----------|-----------|
| LLM | Qwen3.5:2b via Ollama | Qwen 3.5 2B with Gated Delta Networks architecture. CPU-only with swap, ~3.4GB RAM |
| Embeddings | all-MiniLM-L6-v2 | Fast, small (80MB), 384-dim, good quality for semantic search |
| Vector DB | Qdrant | Persistent, REST API, bounded memory, no process restart needed |
| Task Queue | Celery + Redis | Retry, scheduling, status tracking. Redis doubles as session store |
| Web Framework | FastAPI | Async, auto-docs, Pydantic validation, lightweight |
| Frontend | Vanilla JS | No framework deps, fully embeddable, small footprint |

## Memory Budget

Server: 5GB RAM total, ~3GB available for containers.

| Container | mem_limit | Purpose |
|-----------|-----------|---------|
| ollama | 4096MB | LLM model + inference runtime |
| qdrant | 256MB | Vector storage (<1000 apps) |
| redis | 64MB | Task queue, cache, sessions |
| discovery-ranking | 384MB | Embedding model (~200MB) + search |
| chat-intent | 128MB | Intent classifier + routing |
| expert-recommend | 128MB | LLM client + prompts |
| metadata-ingest | 192MB | API client + Celery worker |
| gateway | 128MB | Reverse proxy |
| mock-api | 128MB | Development only |
| **Total** | **~5504MB** | With 4GB swap for Ollama |

## Feature Flags

| Flag | Default | Description |
|------|---------|-------------|
| `RASA_ENABLED` | false | RASA intent classifier (1GB+ RAM) |
| `RERANKER_ENABLED` | false | Cross-encoder reranker (1.1GB RAM) |

These features are disabled by default due to memory constraints but can be enabled on larger servers.
