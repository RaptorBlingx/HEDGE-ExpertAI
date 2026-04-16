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

The stack now includes an optional nginx TLS edge profile. This keeps the
gateway on internal HTTP while exposing only ports 80/443 publicly.

```bash
# Start the base stack (services remain bound to 127.0.0.1 on the host)
docker compose up -d

# Add the TLS edge
docker compose --profile tls up -d nginx
```

The nginx container will:
- use mounted certificates from `TLS_CERT_PATH` / `TLS_KEY_PATH` if provided,
- otherwise generate a short-lived self-signed certificate automatically,
- proxy SSE traffic on `/api/v1/chat/stream` with buffering disabled.

Example production variables in `.env`:

```bash
TLS_SERVER_NAME=hedge.example.com
TLS_CERT_PATH=/etc/letsencrypt/live/hedge.example.com/fullchain.pem
TLS_KEY_PATH=/etc/letsencrypt/live/hedge.example.com/privkey.pem
ENABLE_HSTS=true
TRUST_PROXY_HEADERS=true
CORS_ALLOWED_ORIGINS=https://hedge.example.com
```

If you prefer an external ingress/load balancer, keep the `tls` profile off and
terminate TLS outside Compose instead.

Legacy manual reverse-proxy example:

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

### Auth / Keycloak

The stack now includes an optional Keycloak + Postgres auth profile for local or
staging OIDC setup:

```bash
docker compose --profile auth up -d keycloak-db keycloak
```

Default local access:
- Keycloak admin console: `http://127.0.0.1:${KEYCLOAK_PORT:-8081}`
- Admin user: `KEYCLOAK_ADMIN`

Recommended staged rollout:
1. Enable TLS first.
2. Start Keycloak and configure issuer / audience values.
3. Turn on `OAUTH_ENABLED=true` while keeping `ENABLE_RBAC=false` to validate token parsing.
4. Turn on `ENABLE_RBAC=true` to protect admin and analytics endpoints.

Relevant `.env` values:

```bash
OAUTH_ENABLED=true
ENABLE_RBAC=true
OAUTH_ISSUER=http://127.0.0.1:8081/realms/hedge
OAUTH_AUDIENCE=hedge-expert-api
OAUTH_CLIENT_ID=hedge-expert-api
OAUTH_JWKS_URL=http://keycloak:8080/realms/hedge/protocol/openid-connect/certs
RBAC_ADMIN_ROLES=admin,administrator
RBAC_ANALYST_ROLES=analyst,admin
```

For test-only or bootstrap environments, `OAUTH_SHARED_SECRET` can be used in
place of JWKS-based validation. Do not use that mode in production.

### Protected Endpoints

With `ENABLE_RBAC=true`, the gateway keeps public discovery open but protects:
- `POST /api/v1/ingest/trigger` — admin role
- `GET /api/v1/ingest/status` — analyst/admin role
- `GET /api/v1/feedback/stats` — analyst/admin role
- `GET /api/v1/sessions/recorded*` — analyst/admin role

Chat, search, catalog browsing, app details, and feedback submission remain
public in the first hardening rollout.

### CORS Configuration

Use `.env` for production CORS instead of editing code directly:

```bash
CORS_ALLOWED_ORIGINS=https://your-app-store-domain.com
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
| RASA + Keycloak pressure on 5GB host | Keep `rasa` / `auth` profiles off by default, or move to an 8GB+ node |
| TLS profile serves self-signed cert | Set `TLS_CERT_PATH` and `TLS_KEY_PATH` to real certificate files |
| Admin routes return 401/403 | Verify `OAUTH_ENABLED`, `ENABLE_RBAC`, issuer/audience config, and token roles |
| Qdrant version mismatch | Using `check_compatibility=False` — this is expected |
| Celery tasks not found | Verify `include=["app.tasks.ingest"]` in celery_app.py |
