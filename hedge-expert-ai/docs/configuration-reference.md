# Configuration Reference

Complete reference for all HEDGE-ExpertAI environment variables. All configuration is via environment variables loaded from `.env` files.

---

## Setup

```bash
# Copy the template and customize
cp .env.example .env
```

All defaults are consistent across `.env.example`, `docker-compose.yml`, and `shared/hedge_shared/config.py`.

---

## Variable Reference

### LLM (Ollama)

| Variable | Default | Type | Description |
|---|---|---|---|
| `OLLAMA_BASE_URL` | `http://ollama:11434` | URL | Ollama API base URL |
| `OLLAMA_MODEL` | `qwen3.5:2b` | string | LLM model name. Must be pulled into Ollama first |
| `OLLAMA_TIMEOUT` | `180` | seconds | Request timeout for LLM inference. Increase for larger models on CPU |
| `OLLAMA_THINK` | `false` | bool | Must be `false` for Qwen3.5 (non-thinking mode) |

**Model Options:**

| Model | RAM Required | Speed (CPU) | Notes |
|---|---|---|---|
| `qwen3.5:2b` | ~3.4 GB | ~3 tok/s | Default — best for 5GB servers |
| `qwen3:1.7b` | ~2.5 GB | ~5 tok/s | Lighter alternative |
| `qwen3.5:4b` | ~5.5 GB | ~2 tok/s | Better quality, needs 8GB+ RAM |

### Vector Database (Qdrant)

| Variable | Default | Type | Description |
|---|---|---|---|
| `QDRANT_HOST` | `qdrant` | hostname | Qdrant server hostname |
| `QDRANT_PORT` | `6333` | port | Qdrant REST API port |

### Redis

| Variable | Default | Type | Description |
|---|---|---|---|
| `REDIS_URL` | `redis://redis:6379/0` | URL | Redis connection URL (broker + session store) |

### Embedding Model

| Variable | Default | Type | Description |
|---|---|---|---|
| `EMBEDDING_MODEL` | `all-MiniLM-L6-v2` | string | Sentence-transformer model name. Downloaded on first use (~80MB) |

### Feature Flags

| Variable | Default | Type | Description |
|---|---|---|---|
| `RASA_ENABLED` | `false` | bool | Enable RASA intent classifier. Requires ~1GB additional RAM |
| `RERANKER_ENABLED` | `false` | bool | Enable cross-encoder reranker. Requires ~1.1GB additional RAM |

> **Note:** These features are disabled by default due to the 5GB RAM target. Enable them on servers with 8GB+ RAM.

### App Store API

| Variable | Default | Type | Description |
|---|---|---|---|
| `MOCK_API_URL` | `http://mock-api:9000` | URL | Mock App Store API URL (development) |
| `HEDGE_API_URL` | *(empty)* | URL | Real HEDGE-IoT App Store API URL. When set, overrides mock |

**Behavior:** If `HEDGE_API_URL` is empty, the system uses `MOCK_API_URL` as fallback.

### Ingestion

| Variable | Default | Type | Description |
|---|---|---|---|
| `INGEST_INTERVAL_SECONDS` | `7200` | seconds | Celery Beat schedule for periodic ingestion (2 hours) |

### Service Ports

| Variable | Default | Description |
|---|---|---|
| `GATEWAY_PORT` | `8080` | External-facing gateway port |
| `CHAT_INTENT_PORT` | `8001` | Chat-Intent service port |
| `EXPERT_RECOMMEND_PORT` | `8002` | Expert-Recommend service port |
| `DISCOVERY_RANKING_PORT` | `8003` | Discovery-Ranking service port |
| `METADATA_INGEST_PORT` | `8004` | Metadata-Ingest service port |
| `MOCK_API_PORT` | `9000` | Mock API service port |

### Service URLs (Inter-Service Communication)

| Variable | Default | Description |
|---|---|---|
| `CHAT_INTENT_URL` | `http://chat-intent:8001` | Used by Gateway to proxy chat requests |
| `EXPERT_RECOMMEND_URL` | `http://expert-recommend:8002` | Used by Chat-Intent to call recommendations |
| `DISCOVERY_RANKING_URL` | `http://discovery-ranking:8003` | Used by Expert-Recommend and Metadata-Ingest |
| `METADATA_INGEST_URL` | `http://metadata-ingest:8004` | Used by Gateway for ingest trigger/status |

### General

| Variable | Default | Type | Description |
|---|---|---|---|
| `LOG_LEVEL` | `INFO` | string | Python logging level (`DEBUG`, `INFO`, `WARNING`, `ERROR`) |
| `APP_VERSION` | `0.1.0` | string | Application version (reported in health checks) |

---

## Configuration Precedence

1. Environment variables (highest priority)
2. `.env` file values
3. Defaults in `shared/hedge_shared/config.py` (lowest priority)

---

## Docker Compose Overrides

For local customization, create a `docker-compose.override.yml`:

```yaml
services:
  gateway:
    ports:
      - "3000:8000"    # Change external port
    environment:
      LOG_LEVEL: DEBUG  # Enable debug logging

  ollama:
    mem_limit: 8000m   # More memory for larger models
```

---

## Production Configuration

### Minimum Changes for Production

```bash
# .env (production overrides)

# Set the real App Store API
HEDGE_API_URL=https://appstore.hedge-iot.eu/api

# Reduce ingestion interval
INGEST_INTERVAL_SECONDS=3600

# Set log level
LOG_LEVEL=WARNING
```

### CORS

Update `services/gateway/app/main.py` for production:

```python
allow_origins=["https://appstore.hedge-iot.eu"],
```

### Memory Tuning

For servers with more RAM, enable additional features:

```bash
# 8GB+ server
RASA_ENABLED=true
RERANKER_ENABLED=true
OLLAMA_MODEL=qwen3.5:4b
```
