# Proposal Traceability Matrix

Status is evidence-based: **implemented** means code and focused tests exist; **partial** means meaningful work remains; **pending evidence** means the feature may exist but the proposal claim is not proven. Owners are repository roles until consortium ownership is assigned.

Local gate results and their explicit limitations are retained in
[`evidence/2026-07-31-local-acceptance.md`](evidence/2026-07-31-local-acceptance.md).

| Requirement | Release | Implementation / evidence | Owner | Status |
|---|---:|---|---|---|
| PostgreSQL authoritative catalogue, revisions and outbox | 1 | `database/migrations`, `hedge_shared/storage.py`, live transaction check | Backend | Implemented |
| Separate Valkey cache/session/rate-limit and persistent queue | 1 | Compose services `valkey-cache`, `valkey-queue` | Platform | Implemented |
| Strict quarantine, retry, update and tombstone ingestion | 1 | metadata ingestion task, unit/integration coverage and deterministic Docker ingestion gate | Backend | Partial—delete/tombstone live-stack scenarios still need dedicated acceptance cases |
| Independent PostgreSQL FTS + Qdrant dense RRF | 1 | `searcher_v2.py`; held-out tuning report absent | Search | Partial |
| Audited multilingual E5 and versioned Qdrant alias | 1 | pinned model SHA; live 120-record rebuild and alias promotion; snapshot drill pending | Search | Partial |
| Typed filters and catalogue-revision cache namespace | 1 | `SearchFilters`, lexical/dense filter implementations | Search | Implemented |
| 30-minute authoritative dialogue context | 1 | Valkey sessions and deterministic merge/reset policy | Conversation | Implemented |
| Verified impressions and idempotent events | 1 | PostgreSQL impressions/events and v2 endpoint | Analytics | Implemented |
| Strict v2 OpenAPI/SSE/problem contracts | 1 | generated six-service contracts, SSE media type, typed models, drift gate | API | Implemented |
| Zero Ruff findings / branch coverage ≥80% | 1 | zero Ruff findings; 204 tests; shared core branch coverage 94.21%; enforced in CI | QA | Implemented |
| 120 synthetic apps, ten per 12 SAREF extensions | 2 | deterministic `apps-v2.json`, generator check | Metadata | Implemented |
| Eight-language localized metadata | 2 | all records contain eight locales; linguistic review absent | Metadata | Partial |
| URI-level SAREF profile and JSON-LD | 2 | registry validation, rich annotations and JSON-LD routes | Semantics | Partial—expert review required |
| Multilingual Rasa NLU, 25 examples/intent/language | 2 | 1,600 generated examples, fixed seeded model build, actual Rasa in production/E2E, German native smoke; deterministic app policy | Conversation | Partial—independent native review/F1 evidence absent |
| Follow-up/detail/compare/refine/reset | 2 | persisted context and ordinal/reference handling | Conversation | Partial—eight-language E2E suite pending |
| Licensed provenance-tracked expert corpus | 2 | manifest and exclusion policy | Content | Partial—no approved public HEDGE corpus yet |
| Grounded ordered explanations, no hidden reasoning | 2 | validation, deterministic fallback and stateful `<think>` suppression | AI | Implemented; human accuracy evidence pending |
| Accessible localized widget and verified telemetry | 2 | v3 widget/console, cancellation, session deletion, feedback/open events | Frontend | Partial—WCAG audit pending |
| Public discovery; fail-closed OIDC administration | 3 | gateway policy and production startup validation | Security | Partial—live IdP boundary tests pending |
| Pinned artifacts, SBOM/licence/vulnerability gates | 3 | hashed backend locks; exact npm lock; action/image digests; Python deny policy and reviewed npm allowlist; Python/npm audits; pinned Gitleaks, SPDX SBOM and Grype CI jobs | Supply chain | Partial—NOTICE review and all-image scan evidence pending |
| Non-root/read-only/capability/resource hardening | 3 | Dockerfiles, production overlay and deterministic Docker stack gate; Rasa verified read-only/non-root with no published port | Platform | Partial—full production overlay soak/acceptance pending |
| Metrics and privacy-minimized logs | 3 | Prometheus middleware, no message logging, scheduled transactional 30-day aggregation/erasure | Operations | Partial—dashboard/alerts and target retention evidence pending |
| Backup, snapshots and restore drills | 3 | encrypted three-store backup and disposable restore script; locally passed with PostgreSQL=120, Qdrant=120, Valkey queue restored | Operations | Partial—off-node scheduling/key custody and retained target drill evidence pending |
| TLS/secrets/rollout/rollback | 3 | TLS profile, production validation, protected index promote endpoint | Platform | Partial—automated renewal and secret-file delivery pending |
| HitRate@2 ≥70%, multilingual NLU and explanation gates | 3 | evaluation requirements defined | Evaluation | Pending evidence |
| Acceptance/exposure/discovery/maintenance/satisfaction/uptime KPIs | 3 | verified event model available | Evaluation | Pending consented pilot/before-after evidence |

The real HEDGE Store API is explicitly out of scope. `contracts/hedge-store-v2.schema.json` and `HedgeApiClient` preserve a fail-closed integration boundary without guessing the unavailable contract.
