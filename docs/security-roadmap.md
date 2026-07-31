# Security and Privacy Status

This project is in production hardening, not production-ready.

## Implemented controls

- Anonymous chat/search/catalogue/detail/event routes are separated from OIDC role-protected ingestion, analytics and transcript administration.
- Browser query-string API keys are rejected. The widget supports a same-origin access-token callback.
- Rate limits are distributed through Valkey and keyed by a hashed trusted client/session identity. Production can require fail-closed limiter availability.
- Trusted forwarding headers are accepted only from configured proxy CIDRs.
- Strict request sizes and v2 types, problem responses, request IDs, security headers and explicit CORS configuration are present.
- Logs omit message text and raw session IDs; verified events store a session hash and expire after 30 days. Operational sessions expire after 30 minutes.
- Application images run as UID 10001. The production overlay uses read-only filesystems, dropped capabilities, no-new-privileges, pids and memory limits.
- `APP_ENV=production` rejects permissive origins, default PostgreSQL passwords, shared-secret OIDC, disabled HSTS/RBAC/OIDC or a non-required distributed limiter.
- Hash-verified Python locks, an exact npm lock, immutable action/image pins, Python/npm audits, secret scanning, SPDX SBOM generation and a high-severity dependency gate are configured in CI.
- A daily transaction rolls event-level KPI data into privacy-minimized aggregates after 30 days and erases expired raw impressions/events and consented transcripts.
- Encrypted backup and isolated PostgreSQL/Qdrant/Valkey restore-drill tooling is implemented and locally verified with the 120-record catalogue.

## Gates still required

- Complete the human NOTICE review and all-container vulnerability evidence; package-level licence gates are automated.
- Authenticate internal service traffic and enforce explicit egress/network isolation.
- Complete live authorization, rate-limit, prompt-injection, malformed SSE, dependency-failure and sensitive-log tests.
- Implement the consent/encryption write and authorized deletion APIs for qualitative transcripts.
- Schedule off-node backup replication and retain periodic target-environment restore evidence.
- Integrate renewable external TLS certificates and secret-file delivery in the deployment environment.
- Complete WCAG audit and threat-model review.

No control is considered accepted until its test evidence and owner are recorded in `docs/traceability-matrix.md`.
