# Repository guidance

## Scope and sources

- Respect the task's scope. Preserve unrelated tracked changes and untracked working materials; their presence alone does not block scoped work on a clean tracked tree. Keep secrets and private Store snapshots out of Git. Changes to production data require task authorization.
- Never modify, recreate, restart, or otherwise interfere with `/home/ubuntu/hedge-demo` or its containers, networks, ports, volumes, runtime resources, and recovery guards. Reserve the `hedge` Docker project for the [preserved demo](docs/demo-preservation.md). Use offline/disposable integration tests; `-p` alone does not isolate fixed names or ports.
- Start integration work with [docs/integration-baseline.md](docs/integration-baseline.md). It separates HEDGE-confirmed facts, observed Store v1 contracts, and pending implementation decisions.
- The [proposal](docs/proposals/HEDGE-IoT-OC1-Proposal-HedgeExpertAI.md) defines commitments; it is not the Store API specification. Use current code, Git history, [architecture](docs/architecture.md), [configuration](docs/configuration-reference.md), and [traceability](docs/traceability-matrix.md) to establish implementation status. Dated reports and deliverables describe their own snapshots.
- Do not claim production readiness or proposal KPIs without retained, reviewed evidence. Synthetic catalogue tests and deterministic E2E generation do not establish real Store integration or live-model quality.

## Jira workflow

- Use a dedicated branch for each independently reviewable Jira issue, based on the appropriate integration branch (currently `feat/hedge-store-v1-integration`).
- Run relevant verification and inspect the exact diff before committing. Stage only issue files; commit and push verified work to the existing Forgejo issue branch when safe, preserving unrelated work.
- Never force-push, commit to or merge into `main`, deploy, or alter protected history without explicit approval.
- Report the Jira issue reference, branch, commit, verification performed, and push status; identify blockers and do not invent an issue reference.
- Treat the [2026-10-13 Astra audit](docs/audits/HEDGE-ExpertAI-Astra-Independent-Audit-2026-10-13.md) as investigative evidence. Reproduce findings against current code before implementing fixes; distinguish reported findings from current verification.

## Current architecture

- Python 3.11/FastAPI services: `gateway` → `chat-intent` → `expert-recommend` → `discovery-ranking`; shared models, configuration, security, and storage live in `shared/hedge_shared`.
- Rasa supplies NLU; application code owns dialogue policy. Ollama supplies local generation. Preserve configured model choices unless the task calls for a model change.
- `metadata-ingest` has an API, Celery worker, and scheduler. PostgreSQL holds the durable local catalogue projection, revisions, indexing outbox, and verified events. HEDGE remains authoritative for source metadata and visibility.
- Qdrant is a rebuildable derived vector index. Separate Valkey instances provide bounded operational state and the persistent queue.
- `frontend/angular` is the Angular ExpertAI prototype; reusable assistant components and the typed API adapter live in `src/lib`, separate from the demo shell. `frontend/widget` remains the standalone JavaScript/CSS artifact and `frontend/src` the React/TypeScript validation console. Native HEDGE UI integration is pending; keep all three independent of backend dialogue policy.
- ExpertAI `/api/v2` and HEDGE Store `/api/v1` are independent contracts. `contracts/hedge-store-v2.schema.json` is a synthetic fixture contract, not the real Store contract.

## Engineering judgment

- Make the smallest complete, maintainable change that fixes the root cause at the appropriate existing boundary. Prefer clear, explicit code over cleverness or shortcuts. Simplicity must never compromise correctness, security, or data integrity.
- Reuse established patterns. Add abstractions, wrappers, configuration, dependencies, or layers only for real requirements or demonstrated reuse. Avoid speculative flexibility, boilerplate, duplication, unrelated refactoring, and complexity without demonstrated value.
- Before finishing, review the diff as a maintainer: every change must serve the requirement; remove unnecessary code and verify meaningful behavior and failure cases in proportion to risk. Passing tests alone does not establish good design.

## ExpertAI conversational experience

- Answer directly and naturally. Keep validation internal; avoid repetitive disclaimers, defensive language, robotic templates and explanations of implementation limits.
- Recommend and explain Apps confidently when source evidence supports the user's need. Interpret unfamiliar wording and follow-ups in context; ask a useful clarification when needed, without excessive abstention or invented capabilities.
- Prioritize complete English conversations in the actual widget; refine other languages when requested: understanding, useful recommendations, natural wording, continuity and latency. Automated tests support this product evaluation; they do not replace it. Preserve source grounding and the existing recommendation architecture.

## Engineering and verification

- Code conventions: typed Python, Pydantic contracts, shared helpers, Ruff, and Pytest. Each service has an `app` package; follow existing test import isolation.
- Keep configuration changes consistent across affected shared settings, service environment reads, `.env.example`, Compose profiles, and configuration documentation. Keep secrets out of source and logs.
- Preserve dependency/model/image pins. Python dependencies use hashed `requirements.lock` files; frontends each use their own `package-lock.json` and `npm ci`. CI specifies Python 3.11.15, Node 20.19.4 for the validation console and Node 24.22.0 for Angular; inspect [.github/workflows/ci.yml](.github/workflows/ci.yml) for exact checks.
- Relevant checks: `make lint`, `make test-ci` (80% shared-package branch coverage gate), and frontend checks. API changes require `make openapi` and review of generated `docs/openapi/` diffs.
- Inspect commands before running them. `make e2e`, ingestion/seed, migrations, restore, and stack scripts change state; `make clean` deletes volumes. Run stack checks only in an appropriate isolated environment, with the intended Compose profile.
- For documentation-only changes, check links/sources and run `git diff --check`. Report checks actually run and any limitations.
