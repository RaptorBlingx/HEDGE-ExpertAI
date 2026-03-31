# API Reference

Complete REST API specification for all HEDGE-ExpertAI services.

---

## Table of Contents

- [Gateway API (port 8080)](#gateway-api)
- [Chat Intent API (port 8001)](#chat-intent-api)
- [Expert Recommend API (port 8002)](#expert-recommend-api)
- [Discovery & Ranking API (port 8003)](#discovery--ranking-api)
- [Metadata Ingest API (port 8004)](#metadata-ingest-api)
- [Mock App Store API (port 9000)](#mock-app-store-api)
- [Common Patterns](#common-patterns)

---

## Gateway API

The Gateway is the single entry point for all client traffic. It proxies requests to internal services, applies rate limiting (60 req/min per IP), injects security headers, and provides an aggregated health endpoint.

**Base URL:** `http://localhost:8080`

### `POST /api/v1/chat`

Send a chat message and receive AI-powered recommendations.

**Request:**

```json
{
  "session_id": "optional-uuid",
  "message": "I need an app for monitoring energy consumption"
}
```

| Field | Type | Required | Description |
|---|---|---|---|
| `session_id` | `string \| null` | No | Existing session ID for conversation continuity. Omit to create a new session. |
| `message` | `string` | Yes | User message (min 1 character, max 2000) |

**Response (200):**

```json
{
  "session_id": "a7b3c8d2-1234-5678-abcd-ef0123456789",
  "message": "Here are the most relevant IoT applications for energy monitoring...",
  "intent": "search",
  "apps": [
    {
      "app": {
        "id": "app-001",
        "title": "SmartEnergy Monitor",
        "description": "Real-time energy consumption monitoring...",
        "tags": ["energy", "monitoring", "residential"],
        "saref_type": "Energy",
        "input_datasets": ["smart_meter_readings"],
        "output_datasets": ["energy_consumption_report"],
        "version": "2.1.0",
        "publisher": "GreenTech Solutions"
      },
      "score": 0.8934,
      "vector_score": 0.9212,
      "keyword_score": 0.8500,
      "saref_boost": 1.0
    }
  ]
}
```

| Field | Type | Description |
|---|---|---|
| `session_id` | `string` | Session ID for subsequent messages |
| `message` | `string` | AI-generated response with explanations |
| `intent` | `string` | Classified intent: `search`, `detail`, `greeting`, `help`, `unknown` |
| `apps` | `array` | Recommended apps with relevance scores (empty for non-search intents) |

**Error Responses:**

| Code | Description |
|---|---|
| `429` | Rate limit exceeded (60 req/min per IP) |
| `502` | Chat service unavailable |

---

### `POST /api/v1/apps/search`

Search for apps using hybrid retrieval (vector + keyword + SAREF).

**Request:**

```json
{
  "query": "smart building HVAC solution",
  "top_k": 5,
  "saref_class": "Building"
}
```

| Field | Type | Required | Description |
|---|---|---|---|
| `query` | `string` | Yes | Search query (min 1 character) |
| `top_k` | `integer` | No | Number of results (1–20, default: 5) |
| `saref_class` | `string \| null` | No | SAREF class filter for boosting |

**Response (200):**

```json
{
  "query": "smart building HVAC solution",
  "total": 5,
  "results": [
    {
      "app": { ... },
      "score": 0.8456,
      "vector_score": 0.8912,
      "keyword_score": 0.7500,
      "saref_boost": 1.0
    }
  ]
}
```

---

### `GET /api/v1/apps/{app_id}`

Retrieve a single app by its ID from the vector index.

**Parameters:**

| Parameter | Type | Description |
|---|---|---|
| `app_id` | `string` | Application ID (e.g., `app-001`) |

**Response (200):** Full app metadata object.

**Error:** `404` if app not found in index.

---

### `POST /api/v1/ingest/trigger`

Manually trigger a metadata ingestion cycle.

**Response (200):**

```json
{
  "status": "triggered",
  "task_id": "celery-task-uuid"
}
```

---

### `GET /health`

Aggregated health check across all services.

**Response (200):**

```json
{
  "status": "ok",
  "service": "gateway",
  "version": "0.1.0",
  "services": {
    "gateway": "ok",
    "chat-intent": "ok",
    "expert-recommend": "ok",
    "discovery-ranking": "ok",
    "metadata-ingest": "ok"
  }
}
```

Status values: `ok`, `degraded`, `down`.

---

## Chat Intent API

Internal service for intent classification and session management.

**Base URL:** `http://chat-intent:8001`

### `POST /api/v1/chat`

Classify intent, route to appropriate handler, and manage session.

(Same request/response schema as the Gateway `POST /api/v1/chat`)

### `GET /api/v1/chat/sessions/{session_id}`

Retrieve session history.

**Response (200):**

```json
{
  "session_id": "uuid",
  "messages": [
    {"role": "user", "content": "Find energy apps"},
    {"role": "assistant", "content": "Here are the top..."}
  ],
  "context": {
    "last_results": [ ... ]
  }
}
```

### `DELETE /api/v1/chat/sessions/{session_id}`

End and delete a session.

**Response (200):**

```json
{
  "status": "deleted",
  "session_id": "uuid"
}
```

### `GET /health`

Health check — verifies Redis connectivity.

---

## Expert Recommend API

Internal service for LLM-powered recommendations and explanations.

**Base URL:** `http://expert-recommend:8002`

### `POST /api/v1/recommend`

Full recommendation pipeline: search apps → generate LLM explanation.

**Request:**

```json
{
  "query": "I need an app for energy monitoring",
  "top_k": 5,
  "saref_class": "Energy"
}
```

**Response (200):**

```json
{
  "message": "Based on your query, here are the most relevant applications...",
  "apps": [
    {
      "app": { ... },
      "score": 0.89
    }
  ]
}
```

### `POST /api/v1/explain`

Generate an explanation for a specific app in context of a query.

**Request:**

```json
{
  "query": "What does SmartEnergy Monitor do?",
  "app": {
    "title": "SmartEnergy Monitor",
    "description": "...",
    "tags": ["energy"],
    "saref_type": "Energy",
    "input_datasets": ["smart_meter_readings"],
    "output_datasets": ["energy_consumption_report"]
  }
}
```

**Response (200):**

```json
{
  "query": "What does SmartEnergy Monitor do?",
  "app_title": "SmartEnergy Monitor",
  "explanation": "SmartEnergy Monitor tracks real-time electricity, gas, and water usage..."
}
```

### `GET /health`

Health check — verifies Ollama LLM connectivity.

---

## Discovery & Ranking API

Internal service for hybrid search and vector indexing.

**Base URL:** `http://discovery-ranking:8003`

### `POST /api/v1/apps/search`

Hybrid search combining vector similarity, keyword matching, and SAREF boost.

**Scoring formula:** `0.6 × vector + 0.3 × keyword + 0.1 × saref`

**Request:**

```json
{
  "query": "precision irrigation for farming",
  "top_k": 5,
  "saref_class": "Agriculture"
}
```

**Response (200):**

```json
{
  "query": "precision irrigation for farming",
  "total": 5,
  "results": [
    {
      "app": {
        "id": "app-004",
        "title": "SmartIrrigation Controller",
        "description": "...",
        "tags": ["irrigation", "agriculture"],
        "saref_type": "Agriculture",
        "input_datasets": ["soil_moisture_sensors"],
        "output_datasets": ["irrigation_schedule"]
      },
      "score": 0.9123,
      "vector_score": 0.9456,
      "keyword_score": 0.8333,
      "saref_boost": 1.0
    }
  ]
}
```

### `POST /api/v1/apps/index`

Index a batch of apps into the vector store.

**Request:**

```json
{
  "apps": [
    {
      "id": "app-001",
      "title": "SmartEnergy Monitor",
      "description": "...",
      "tags": ["energy"],
      "saref_type": "Energy"
    }
  ]
}
```

**Response (200):**

```json
{
  "indexed": 1
}
```

### `GET /api/v1/apps/{app_id}`

Retrieve a single app by ID from the Qdrant vector index.

### `GET /health`

Health check — verifies Qdrant connectivity.

---

## Metadata Ingest API

Internal service for automated App Store metadata synchronization.

**Base URL:** `http://metadata-ingest:8004`

### `POST /api/v1/ingest/trigger`

Manually trigger an ingestion cycle via Celery.

**Response (200):**

```json
{
  "status": "triggered",
  "task_id": "celery-task-uuid"
}
```

### `GET /api/v1/ingest/status`

Get the status and statistics of the last ingestion run.

**Response (200):**

```json
{
  "last_run": "2026-03-31T12:00:00+00:00",
  "stats": {
    "total_fetched": "50",
    "new": "3",
    "updated": "1",
    "unchanged": "46"
  }
}
```

### `GET /health`

Health check — verifies Redis connectivity.

---

## Mock App Store API

Development-only mock of the HEDGE-IoT App Store API with 50 seed applications.

**Base URL:** `http://mock-api:9000`

### `GET /api/apps`

List all apps with pagination.

**Query Parameters:**

| Parameter | Type | Default | Description |
|---|---|---|---|
| `page` | `integer` | 1 | Page number (≥ 1) |
| `page_size` | `integer` | 20 | Results per page (1–100) |

**Response (200):**

```json
{
  "total": 50,
  "page": 1,
  "page_size": 20,
  "apps": [ ... ]
}
```

### `GET /api/apps/search?q={query}`

Basic keyword search across title, description, and tags.

### `GET /api/apps/{app_id}`

Get a single app by ID.

### `GET /health`

Health check.

---

## Common Patterns

### Authentication

Currently no authentication is required. For production, configure API keys or OAuth at the Gateway level.

### Rate Limiting

The Gateway enforces **60 requests per minute per IP**. Health check endpoints (`/health`) are excluded from rate limiting.

**Response when exceeded:**

```json
{
  "detail": "Rate limit exceeded. Try again later."
}
```

### Security Headers

All Gateway responses include:

| Header | Value |
|---|---|
| `X-Content-Type-Options` | `nosniff` |
| `X-Frame-Options` | `DENY` |
| `X-XSS-Protection` | `1; mode=block` |
| `Referrer-Policy` | `strict-origin-when-cross-origin` |
| `X-Request-ID` | Unique UUID per request |

### Error Responses

Standard error format:

```json
{
  "detail": "Human-readable error message"
}
```

### Timeouts

| Route | Timeout | Reason |
|---|---|---|
| Chat (LLM) | 300s | CPU inference can be slow |
| Search | 30s | Embedding + vector search |
| Explanation | 180s | LLM generation |
| Ingest | 120s | Batch API fetch + index |
| App detail | 10s | Simple retrieval |
| Health check | 5s | Quick connectivity test |
