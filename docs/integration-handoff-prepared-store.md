# Fast Store integration handoff

Local finalization of `perf/prepared-store-discovery`, starting at `3c25351`.

**Integration follow-up:** [accepted Store integration](store-fast-integration.md)
reconciles this handoff with the remote head. Its permanent
[frontend dependency policy](security/frontend-dependency-policy.md) supersedes
the temporary npm exception described in this historical handoff.
The remote `feat/hedge-store-v1-integration` head was checked with authenticated
Git and remains `0a02b5ad2da74222fd85b10b6a3b2c998025db9d`. No push, branch merge,
deployment, Jira operation or upstream Store mutation was performed.

## What is ready

Real backend Keycloak client credentials, renewal, authorized Store synchronization,
native identity, publication gates, incremental indexing and automatic English
preparation are retained. Ordinary chat remains generation-free. Finalization fixes:

- Connected source assertions now bind an explicit current-App actor to an adjacent
  passive statement about the same plural object. This recognizes the demonstrated
  aggregation capability without requiring a hand-authored App explanation.
  Unknown actors, negation, dependencies, unfamiliar tails, real numeric limits and
  conditional capabilities remain uncertain. A clearly contrasted pilot/trial size
  is scoped to that sample only when the same sentence explicitly says the platform
  accommodates more; it is not treated as a platform capacity ceiling.
- Simplification uses the current explanation topic and prepared fact, then provides
  a shorter restatement on a repeated request. A small English vocabulary explains
  technical nouns/actions; these display words are not indexed or independent
  recommendation evidence. No App names or exact question-answer lookup was added.
- A numeric zero price, including `billable=false`, does not establish free use.
  English cost answers state that terms are unconfirmed and retain the Store value.
  Numeric/price source fields themselves are unchanged. Free-only filtering remains
  conservative. Positive prices and missing prices retain their existing handling.

Preparation advances from version 3 to **4**. It adds source-bound active/short
renderings and explicit qualification flags. The reader reproduces preparation
against current evidence; unparsed qualifications cannot be cleared by a shorter
rendering. The existing sole suitability assessor still decides recommendations.
No runtime LLM, new service, model change, dependency update or Turkish refinement.

## Ancestry and prerequisites

The common ancestor is `c881c6d`. All application, shared, frontend and database
files at `0a02b5a` match that SCRUM-39 head. Target-only changes are the merge,
acceptance/security records and CI policy. Do not reapply SCRUM-39.

| Source commit | Include once | Review boundary |
|---|---|---|
| `de2fc1b` | Required prerequisite | Composes existing Store work through `c6050ab` onto SCRUM-39: private durable workspace, source membership, contextual chat, widget and migration 0004. It is a substantial 45-file prerequisite, not a small performance-only change. |
| `0ed1533` | Required | Prepared knowledge/migration 0005, incremental cache/index use, routine generation-free requests, optional-generation readiness and its OpenAPI description. |
| `84f93fe` | Required | Conversation composition, references, optional reviewed prose importer and concise AGENTS conversational guidance. Existing Turkish support is retained, not expanded in finalization. |
| `2a1945e`, `3c25351` | Required | Backend M2M provider/configuration, automatic English preparation, live-data annotation scope fixes and actual Store evidence. The initial credential-import failure finding is superseded by verified live success. |
| Finalization after `3c25351` | Required | The three demonstrated regression fixes, safety checks, populated-schema upgrade/rollback verification and this handoff. |

Do not additionally replay `bd8de29`–`c881c6d` or the original
`b5f2df0`/`3ee84f4`/`4fa7a6e`/`c6050ab` Store commits: the former are already in the
target and the latter are composed in `de2fc1b`. Dropping the prerequisite while
cherry-picking only performance/authentication commits leaves missing services,
state and migrations. No separate experimental branch is part of this handoff.

A three-way merge simulation is the appropriate comparison. A direct two-tree
`git diff 0a02b5a perf/prepared-store-discovery` misleadingly shows target-only
security files as deletions; **do not use that diff as a replacement patch**.
The simulated integration retains the target CI workflow, audit checker/tests,
exception record, acceptance history and audit-report ignore rule byte-for-byte.
It adds the conversational section to AGENTS and prioritizes English without
replacing the target's architecture, demo-preservation or verification guidance.
The private handoff contains a patch generated against the *simulated result*,
not an overwrite of target-only work. No actual merge commit or branch move is
needed to inspect that tree.

## Database and activation order

The target has migrations 0001–0003. Apply both additive migrations through the
existing migration runner, against the explicitly selected authorized database,
before starting code that reads the new columns/tables:

1. `0004_store_sync`: private observation state and source-scoped membership,
   including applied index revisions/availability.
2. `0005_store_knowledge`: nullable JSONB `catalog_apps.prepared_knowledge`.

Migration execution remains advisory-lock protected and exactly-once tracked.
Neither migration changes authoritative App payloads, native IDs, source revisions,
revision history or existing outbox rows. Existing Store rows can rebuild derived
preparation on startup without claiming a new upstream observation. A preparer
version change causes one scoped vector rebuild; unchanged source/model/preparation
then reuses it. Vectors remain derived; lexical retrieval survives index lag.

A populated 0003-schema test preserves synthetic and native Store rows, source
checksums/revisions, history and outbox through upgrade and repeated migration.
It rebuilds preparation, then exercises 0005/0004 down SQL in the disposable schema
and confirms authoritative rows survive. This is not a production rollback run.
For a later approved rollback, stop new Store readers first, remove derived 0005
before membership 0004, and manage migration-version records consistently with the
migration tooling; never leave old code reading dropped fields. Preserve source
rows and storage. No migration was run against the preserved demo or production.

## Existing services and authentication configuration

Keep the current gateway → chat-intent → expert-recommend → discovery-ranking,
metadata-ingest API/worker/scheduler, PostgreSQL, Qdrant, Valkey, Rasa and optional
Ollama. The private workspace is a validation adapter over those implementations:
browser HTTP/SSE and outbound Store HTTPS are real, while internal calls use
in-process bridges. It is not proof of a deployed service mesh or native Angular
pane. Generic synthetic ingestion and public Store indexing activation are still
separate, disabled-by-default boundaries; do not silently enable them during merge.

Backend M2M configuration, distinct from incoming ExpertAI/user OIDC:

- Set `HEDGE_STORE_ISSUER`, `HEDGE_STORE_CLIENT_ID`,
  `HEDGE_STORE_CLIENT_SECRET_FILE` and the existing Store ID/API base.
- Use an owned mode-0600 regular secret file and a backend-only read-only mount.
  No credential value, access token or private Store snapshot belongs in Git,
  frontend settings, deployment examples, command arguments or handoff patches.
- Configure exactly one credential source. Leave `HEDGE_STORE_TOKEN_FILE` empty
  for M2M; the legacy externally rotated Bearer-file path is still supported.
- TLS/issuer/endpoint checks, bounded requests, in-memory token caching, early
  renewal and one bounded Store-401 renewal are retained. Production/user security
  checks are not weakened. No user-list or asset permission is assumed.
- The private launcher exposes names/paths/port overrides for isolation. This task
  uses only `expertai-store-m2m` / loopback 8094. The original workspace and demo
  remain untouched. Default polling remains daily; publication-to-search ≤2 hours
  is not established by unchanged polls and still needs cadence/target acceptance.

## CI/security handoff

Preserve `0a02b5a`'s security workflow and records. Current audits still report
**8 high + 4 moderate, unchanged development-only findings, zero production
findings**, with byte-identical frontend manifests. The existing target-branch
checker accepts only those exact findings through `2026-10-26T00:00:00Z`
(03:00 Istanbul), tied to remediation **SCRUM-60**. It rejects changed findings,
production vulnerabilities, manifest changes, wrong branches and expiry.
No exception was broadened, renewed or copied onto the performance branch.

The performance branch's old standalone full audit still exits 1. The proposed
integration uses the target's already-approved checker and production audit.
This is an explicit exception, not a clean full audit. A maintainer integrating
after expiry or after an advisory/manifest change must resolve the gate through
the established policy; this handoff supplies no new waiver.

CI specifies Python 3.11.15 / Node 20.19.4, Ruff, ≥80% shared branch coverage,
OpenAPI consistency, deterministic asset checks, backend security/licence checks,
frontend licence/tests/audit/build, E2E and supply-chain jobs. Source/module pins
are unchanged. The only existing OpenAPI difference from the target is the
optional-generation health description; all six exports reproduce the branch.
Remote CI was not triggered or claimed green: no push was authorized. The workflow
push filter covers `feat/**`, not this `perf/**` branch, and PR filtering names
`main`; follow the existing maintainer CI workflow for the eventual integration.

## Evidence and remaining limits

The private finalization directory retains complete unedited before/after English
widget conversations, raw SSE/native IDs/decisions, screenshots, fresh Store refresh
receipt, timings, unit/integration/upgrade checks, frontend tests/build, full and
production audits, target-policy assessment and merge-simulation evidence.
Only two Apps are currently observed under the authorized client. That proves
neither global catalogue completeness nor large-real-catalogue recommendation quality.
Explicit source inspection remains technical; unknown language/complex grammar can
still fall back to source text or abstain. Native UI, full deployed-service testing,
real upstream lifecycle mutation/freshness measurement and dependency remediation
remain separate work. They are not silently claimed complete by a local merge review.
