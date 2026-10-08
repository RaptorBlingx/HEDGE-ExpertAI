# Repository guidance

## Scope and sources

- Respect the task's scope. Preserve unrelated tracked changes and untracked working materials. Deployment, pushing, and changes to production data require task authorization.
- On this host, reserve the `hedge` Docker project, fixed containers/ports/volumes, and local recovery guards for the [preserved demo](docs/demo-preservation.md). Use offline/disposable integration tests; `-p` alone does not isolate fixed names or ports.
- Start integration work with [docs/integration-baseline.md](docs/integration-baseline.md). It separates HEDGE-confirmed facts, observed Store v1 contracts, and pending implementation decisions.
- The [proposal](docs/proposals/HEDGE-IoT-OC1-Proposal-HedgeExpertAI.md) defines commitments; it is not the Store API specification. Use current code, Git history, [architecture](docs/architecture.md), [configuration](docs/configuration-reference.md), and [traceability](docs/traceability-matrix.md) to establish implementation status. Dated reports and deliverables describe their own snapshots.
- Do not claim production readiness or proposal KPIs without retained, reviewed evidence. Synthetic catalogue tests and deterministic E2E generation do not establish real Store integration or live-model quality.

## Current architecture

- Python 3.11/FastAPI services: `gateway` → `chat-intent` → `expert-recommend` → `discovery-ranking`; shared models, configuration, security, and storage live in `shared/hedge_shared`.
- Rasa supplies NLU; application code owns dialogue policy. Ollama supplies local generation. Preserve configured model choices unless the task calls for a model change.
- `metadata-ingest` has an API, Celery worker, and scheduler. PostgreSQL holds the durable local catalogue projection, revisions, indexing outbox, and verified events. HEDGE remains authoritative for source metadata and visibility.
- Qdrant is a rebuildable derived vector index. Separate Valkey instances provide bounded operational state and the persistent queue.
- `frontend/widget` is a standalone JavaScript/CSS delivery artifact; `frontend/src` is the React/TypeScript validation console. Native HEDGE UI integration is pending.
- ExpertAI `/api/v2` and HEDGE Store `/api/v1` are independent contracts. `contracts/hedge-store-v2.schema.json` is a synthetic fixture contract, not the real Store contract.

## Engineering judgment

- Make the smallest complete, maintainable change that fixes the root cause at the appropriate existing boundary. Prefer clear, explicit code over cleverness or shortcuts. Simplicity must never compromise correctness, security, or data integrity.
- Reuse established patterns. Add abstractions, wrappers, configuration, dependencies, or layers only for real requirements or demonstrated reuse. Avoid speculative flexibility, boilerplate, duplication, unrelated refactoring, and complexity without demonstrated value.
- Before finishing, review the diff as a maintainer: every change must serve the requirement; remove unnecessary code and verify meaningful behavior and failure cases in proportion to risk. Passing tests alone does not establish good design.

## Engineering and verification

- Code conventions: typed Python, Pydantic contracts, shared helpers, Ruff, and Pytest. Each service has an `app` package; follow existing test import isolation.
- Keep configuration changes consistent across affected shared settings, service environment reads, `.env.example`, Compose profiles, and configuration documentation. Keep secrets out of source and logs.
- Preserve dependency/model/image pins. Python dependencies use hashed `requirements.lock` files; frontend uses `package-lock.json` and `npm ci`. CI currently specifies Python 3.11.15 and Node 20.19.4; inspect [.github/workflows/ci.yml](.github/workflows/ci.yml) for exact checks.
- Relevant checks: `make lint`, `make test-ci` (80% shared-package branch coverage gate), and frontend checks. API changes require `make openapi` and review of generated `docs/openapi/` diffs.
- Inspect commands before running them. `make e2e`, ingestion/seed, migrations, restore, and stack scripts change state; `make clean` deletes volumes. Run stack checks only in an appropriate isolated environment, with the intended Compose profile.
- For documentation-only changes, check links/sources and run `git diff --check`. Report checks actually run and any limitations.
