# Deployment Guide

## Prerequisites

- Docker Engine 24+ and Docker Compose v2
- Minimum 5GB RAM (8GB+ recommended)
- ~10GB disk for images and models
- Linux x86_64 (tested on Ubuntu 22.04)

## Initial Setup

### 1. Clone the repository

```bash
git clone git@github.com:RaptorBlingx/HEDGE-ExpertAI.git
cd HEDGE-ExpertAI
```

### 2. Configure environment

```bash
cp .env.example .env
# Edit .env if needed (defaults work for standard deployment)
```

### 3. Enable swap (recommended for 5GB servers)

```bash
sudo fallocate -l 4G /swapfile
sudo chmod 600 /swapfile
sudo mkswap /swapfile
sudo swapon /swapfile
echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab
```

### 4. Build and start

```bash
make build
make up
```

### 5. Pull the LLM model

```bash
make pull-model
```

This downloads qwen3.5:2b (~2.7GB). On first run, discovery-ranking will also download the embedding model (~80MB). Allow 5-10 minutes for initial startup. Requires 4GB swap configured (see deployment guide).

### 6. Seed the search index

```bash
make seed
```

### 7. Verify all services

```bash
make health
```

All services should report "ok" or "degraded" (degraded is normal if Ollama model is still loading).

### 8. Run evaluation (optional)

```bash
# Search quality only (fast, no LLM needed)
make evaluate-search

# Full evaluation including chat and streaming
make evaluate
```

## Production Considerations

### TLS/HTTPS

Add a reverse proxy (nginx, Caddy, Traefik) in front of the gateway:

```nginx
server {
    listen 443 ssl;
    server_name your-domain.com;

    ssl_certificate /etc/ssl/cert.pem;
    ssl_certificate_key /etc/ssl/key.pem;

    location / {
        proxy_pass http://localhost:8080;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_read_timeout 300s;
    }
}
```

### CORS Configuration

Update `CORS allow_origins` in `services/gateway/app/main.py` for production:

```python
allow_origins=["https://your-app-store-domain.com"],
```

### Monitoring

```bash
# Watch container resource usage
docker stats

# Check service logs
make logs

# Check ingestion status
curl http://localhost:8080/api/v1/ingest/status
```

### Upgrading the LLM Model

To switch to a larger model (requires more RAM):

```bash
# Edit .env
OLLAMA_MODEL=qwen3:1.7b

# Pull new model
docker compose exec ollama ollama pull qwen3:1.7b

# Restart services
make down && make up
```

### Backup

```bash
# Backup volumes
docker run --rm -v "$(basename "$PWD")_qdrant-data:/data" -v "$(pwd)/backups:/backup" alpine tar czf "/backup/qdrant-$(date +%Y%m%d).tar.gz" /data
docker run --rm -v "$(basename "$PWD")_redis-data:/data" -v "$(pwd)/backups:/backup" alpine tar czf "/backup/redis-$(date +%Y%m%d).tar.gz" /data
```

## Troubleshooting

| Issue | Solution |
|-------|----------|
| discovery-ranking fails healthcheck | Allow 3+ minutes for model download on first start (`start_period: 180s`) |
| Ollama timeout errors | Increase `OLLAMA_TIMEOUT` in `.env` (default: 180s, try 240s) |
| Out of memory (OOM kill) | Enable swap, or reduce `mem_limit` values and use smaller model |
| Qdrant version mismatch | Using `check_compatibility=False` — this is expected |
| Celery tasks not found | Verify `include=["app.tasks.ingest"]` in celery_app.py |
