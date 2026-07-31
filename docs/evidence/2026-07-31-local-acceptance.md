# Local Acceptance Evidence — 31 July 2026

**Scope:** `feat/proposal-completion-hardening` working tree on the development
node. This is engineering evidence, not HEDGE/consortium approval and not a
production-readiness or proposal-KPI pass declaration.

## Reproducible quality gates

| Gate | Retained result |
|---|---|
| Backend tests | 205 passed on Python 3.11.15 |
| Shared core branch coverage | 94.28% (80% gate passed) |
| Ruff | zero findings across shared, services, tests, scripts, evaluation, and migrations |
| Python dependency audit | seven hash-locked runtime graphs; no known vulnerabilities reported by `pip-audit 2.9.0` |
| Frontend | one component test passed; Vite 7.3.6 production build passed |
| npm audit | zero known vulnerabilities after `npm ci` |
| npm licence policy | 332 installed packages passed the reviewed exact allowlist |
| Generated assets | 120 catalogue records, 1,600 NLU examples, and 200 provisional evaluation queries reproduced exactly |
| Contracts | six OpenAPI documents regenerated; v2 streaming exposes only `text/event-stream` |

One upstream warning remains: Starlette 1.3.1 deprecates its current `httpx`
TestClient adapter in favor of the emerging `httpx2` package. It does not fail
the suite and no unreviewed replacement dependency has been introduced.

## Live dependency and data-path checks

- PostgreSQL migrations `0001_initial` and `0002_retention_aggregates` applied
  once under an advisory lock.
- Transactional synthetic-catalogue ingestion completed with 120 searchable
  records and no failed items.
- Independent PostgreSQL full-text and Qdrant dense retrieval returned localized
  and typed-filtered results.
- Two 120-record physical Qdrant collections were rebuilt and promoted; alias
  rollback to the previous validated collection succeeded without opening the
  legacy volume in place.
- An expired KPI event was aggregated without App/session identifiers and its
  raw impression/event was deleted in the same transaction.

## Deterministic Docker acceptance

The real gateway, chat-intent, expert-recommend, discovery-ranking,
metadata-ingest API/worker/scheduler, PostgreSQL, separate Valkey instances,
Qdrant, mock Store fixture, and Rasa ran together. Only generation was replaced
by an intentionally untrusted deterministic Ollama-compatible fixture.

The acceptance script verified:

1. the pinned, telemetry-disabled Rasa model classified the native German text
   `Zeige mir Anwendungen zur Energieüberwachung` as `search` with confidence
   `1.0`;
2. a v2 ingestion run completed;
3. German SAREF4ENER-filtered hybrid retrieval returned two results;
4. SSE emitted `stage`, `recommendations`, `explanation_delta`, and `complete`;
5. no `<think>` tag was emitted.

The production Rasa container was separately verified healthy with a read-only
root filesystem, all Linux capabilities dropped, and no published host port.

## Recovery drill

The backup tool created checksum-protected AES-256-CBC/PBKDF2 encrypted
PostgreSQL, Qdrant, and persistent Valkey queue artifacts. The restore tool then
used disposable containers and verified:

| Store | Restored evidence |
|---|---:|
| PostgreSQL active catalogue | 120 records |
| Qdrant collection | 120 vectors |
| Valkey persistent queue | 23 keys at drill time |

No live database, collection alias, or volume was overwritten. Temporary drill
artifacts and containers were removed after verification.

## Evidence still required

- held-out/native eight-language NLU F1 and retrieval labels;
- human claim-to-evidence explanation review;
- target-node concurrency, latency, soak, freshness, and availability evidence;
- live OIDC authorization and external TLS/renewal acceptance;
- all-image vulnerability review and human NOTICE approval;
- scheduled off-node backups and retained target-environment restore drills;
- consented pilot/before-and-after evidence for proposal outcome KPIs.
