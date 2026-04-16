# HEDGE-ExpertAI Security Roadmap

## Current State (OC1)

### Implemented
- **API Key Authentication**: Optional `GATEWAY_API_KEY` via `X-API-Key` header
- **Rate Limiting**: 60 req/min per IP (in-memory, gateway-level)
- **Security Headers**: X-Content-Type-Options, X-Frame-Options, X-XSS-Protection, Referrer-Policy, Permissions-Policy, Content-Security-Policy
- **CORS**: Configurable via `CORS_ALLOWED_ORIGINS` (default: permissive for dev)
- **Request IDs**: UUID tracing via `X-Request-ID` header
- **Input Validation**: Pydantic models with field constraints on all endpoints
- **No PII Storage**: Only session IDs are stored; no user credentials or personal data

### Environment Variables
| Variable | Purpose | Default |
|----------|---------|---------|
| `GATEWAY_API_KEY` | API key for gateway auth | *(empty = open access)* |
| `CORS_ALLOWED_ORIGINS` | Comma-separated allowed origins | `*` |
| `ENABLE_HSTS` | Enable HSTS header (requires TLS termination) | `false` |

## Roadmap for Production (OC2 / TRL 8)

### Phase 1: TLS Termination
- Add nginx reverse proxy profile inside Docker Compose (implemented) or use an external ingress
- Support mounted certificates or short-lived self-signed certificates for local validation
- Enable `ENABLE_HSTS=true` for Strict-Transport-Security
- Inter-service communication remains HTTP (inside Docker network)

### Phase 2: RBAC & OAuth
- Integrate self-hosted Keycloak first, then switch to HEDGE-IoT identity provider when available
- Define roles: `viewer` (search/chat), `admin` (ingest trigger), `analyst` (session export / stats)
- Validate JWTs at the gateway using JWKS, keeping API key as a temporary fallback
- Keep discovery endpoints public in the first rollout; protect only admin and analytics routes

### Phase 3: Key Rotation
- Implement periodic API key rotation mechanism
- Add key versioning to support rolling updates
- Audit log for key usage

### Phase 4: Log Anonymization
- Hash session IDs in logs
- Redact IP addresses after rate-limit window
- GDPR-compliant retention policy (30 days)

### Phase 5: Container Hardening
- Run containers as non-root user
- Read-only filesystem where possible
- Scan images with Trivy/Snyk in CI pipeline
- Pin base image digests

## Current Implementation Notes

- Internal service host ports are now bound to `127.0.0.1` by default to reduce accidental exposure.
- Optional profiles:
	- `tls` → nginx edge on ports 80/443
	- `auth` → Keycloak + Postgres
	- `rasa` / `full` → RASA NLU service
- RASA activation is implemented as RASA-first with regex fallback, low-confidence fallback, and a short circuit breaker to avoid chat outages.
