# Store v1 Phase 1: offline source metadata

Implemented locally against `fa06952` and the integration baseline. This phase
adds source normalization and durable identity support. It does not connect the
Store, authenticate outbound requests, ingest snapshots, or establish production
readiness.

## Boundary and mapping

`services/metadata-ingest/app/client.py::normalize_store_v1_app` takes one App
object and returns `hedge_shared.store_v1.StoreAppMetadata`. It performs no I/O.
The public Store OpenAPI was checked on 2026-10-08; its SHA-256 remains
`f5090c9cad06ea314a70ca1676dc433d97006ddbd7a65f9273058480239793a3`, matching
the [baseline](integration-baseline.md). The [contract fixtures](../tests/fixtures/store-v1/apps.json)
are constructed examples of the documented shape, not authenticated HEDGE data.

| Source | Local representation and limits |
|---|---|
| `fkAppStoreId` + `appId` | Opaque, case-sensitive native identity. Both must be nonblank strings without surrounding whitespace. A scoped endpoint Store ID may supply a missing/null `fkAppStoreId`; a mismatch fails validation. No UUID format is assumed. |
| Native pair | Retained as `store_id` and `app_id`; local `id` is `store-v1-` plus SHA-256 of the ordered JSON pair. It does not replace the native IDs. Delimiter ambiguity and cross-Store App ID collisions are avoided. |
| `name`, `description`, `provider`, `readme` | Optional source strings. Blank text becomes missing; no title, summary, publisher, language, licence, taxonomy, or SAREF assertion is invented. |
| `visible`, `active` | Strict boolean or unknown (`None`), preserving the distinction between false and absent. `public_eligible` conservatively requires both flags to be explicitly true. No certification status is used as a publication gate. |
| `registrationDate` | Optional timezone-aware ISO date-time; numeric timestamps and malformed values fail. Never used as an update timestamp. |
| `uiUrl`, `openAPIURL`, `deployURL`, `registryBaseURL` | Optional HTTP(S) URLs, retained by their source role. None is asserted to be a canonical Store detail or documentation link. |
| `appVersionList` | Optional versions in source order with IDs, version strings, registration dates and comments. No latest/current version is chosen; supplied `fkAppId` must match the parent App. |
| Unknown fields and asset descriptions | Ignored by this minimal projection; they cannot inject local identity or eligibility. No App/asset join is inferred. |

Non-object records, missing identity, and malformed known fields raise
`ValueError`/Pydantic `ValidationError` for later record-level quarantine. They
do not produce partially fabricated Apps. Optional fields do not become new
required upstream properties merely because the synthetic profile requires them.
Null/absent versions stay missing; an explicitly empty version list stays empty.

## Persistence and compatibility

Migration `0003_store_identity` adds nullable native identity columns and a unique
Store/App pair index to the existing `catalog_apps` projection. Existing IDs,
payloads, revisions, searchability and outbox entries remain unchanged. The
existing migration runner applies it transactionally once. Apply this migration
before running updated storage code, including synthetic ingestion. Downgrade refuses to
remove native identity while Store source rows exist; preserve/export those rows
before any intentional downgrade. No migration was run against a live database.

`upsert_catalogue_app` accepts either strict `AppMetadataV2` or the sparse Store
profile. Store rows use the database discriminator `hedge-store-v1`, not synthetic
`2.0`. Their payloads and revision history retain native identity and publication
facts; the database `active` column holds conservative public eligibility. A
transaction advisory lock serializes concurrent first inserts of one Store/App
identity. Cross-profile key collisions are rejected before overwriting data.

Store rows remain offline: no indexing outbox entries are created. Existing v2
detail/list/search/cache-revision reads and synthetic snapshot retirement only
operate on `2.0` rows. This protects both contracts while consumers still require
the rich synthetic shape. The scheduler, client factory, synthetic contract and
legacy transport behavior are unchanged. Source records must not be wired into
live ingestion or public recommendations until the later transport,
reconciliation and retrieval safety work is complete.

## Assumptions requiring authenticated HEDGE payloads

- Confirm `active` semantics and service-client visibility, including published,
  unpublished and withdrawn Apps. The explicit-both-true eligibility rule fails
  closed pending that confirmation; it may exclude otherwise published records.
- Confirm identity presence, endpoint context for missing Store IDs, string
  `provider` as documented, null/blank optional fields, timestamp timezones, URL
  contents and version ordering. A malformed known optional field currently
  rejects that record rather than silently discarding evidence.
- Confirm public corpus rights, canonical navigation links, App/asset joins and
  any actual last-update field. They remain unmapped. Unknown source fields are
  not archived in this projection; future ingestion quarantine may retain raw
  payloads under the approved data policy.

## Original Phase 1 verification report

The attached patch supplied the following verification summary from the original
checkout; this is distinct from the import verification below.

Local Python 3.11.16 test container with the repository's hashed dependency locks
and pinned Pytest/Ruff tools; isolated PostgreSQL 16.9 using the Compose image pin.
No running HEDGE services or external catalogue data were used.

- Final combined run: 223 unit tests and 6 isolated PostgreSQL tests passed
  (229 total), with 96.59% shared branch coverage against the required 80% gate.
  A pre-existing Starlette/httpx deprecation warning remains.
- Dedicated PostgreSQL regression tests cover additive upgrade, repeat migration
  runner, native uniqueness, publication revisions, concurrent inserts, synthetic
  compatibility, source isolation and the guarded downgrade.
- Repository Ruff lint and OpenAPI export; public API contracts are unchanged.
- Final diff reviewed for scope and complexity: existing repository storage and
  revision paths are reused, with one source model module, an offline normalizer,
  and an additive migration. No new service, dependency, configuration, transport
  or catalogue table.

To repeat the database tests, provide `HEDGE_TEST_DATABASE_URL` for a disposable
database named `hedge_phase1_test`, then run
`python -m pytest tests/integration/test_store_v1_persistence.py -q`.
The tests create and drop only their own temporary schema.

## Import verification (2026-10-08)

Phase 1 was absent from `/home/ubuntu/hedge` on branch
`docs/hedge-review-materials` at `fa06952`. The supplied patch applied cleanly;
its code, migrations, fixtures, and tests were imported without reimplementation.
Existing agent guidance, local documentation work, and demo assets/configuration
were preserved. The baseline was updated to distinguish completed offline work
from pending live integration.

- Python 3.11.15 in a disposable test image with repository hashed dependency
  locks and CI-pinned Pytest/Ruff: **223 unit tests passed**, with **94.88%**
  shared-package branch-aware coverage against the 80% gate. The existing
  Starlette/httpx deprecation warning remains.
- **Six persistence tests passed** on disposable PostgreSQL 16.9, using a
  separate internal network, no published ports, and temporary database storage.
  Migrations ran only in that test database; the running demo database was untouched.
- Repository Ruff passed. OpenAPI was exported in a temporary source copy;
  all six outputs matched the checked-in contracts byte for byte.
- Documentation links, whitespace, imported patch contents, and preservation
  of prior changes were checked. HEAD and the index remain unchanged; no demo
  container was rebuilt, restarted, or replaced. Disposable test resources
  were removed after verification.

At import, outbound authentication/transport and safe snapshot reconciliation
remained pending; the subsequent reconciliation slice is recorded below.
Migration `0003_store_identity` remains a prerequisite
before running updated storage code against any non-test database; no live
migration, ingestion, deployment, or push was performed.

## Safe snapshot reconciliation slice (2026-10-08)

[`reconcile_catalogue_snapshot`](../services/metadata-ingest/app/snapshot.py)
now fetches **inside** a PostgreSQL transaction advisory lock, scoped by native
Store ID (synthetic profile: exact ingestion source string). The lock spans
fetch, validation, projection, revisions, quarantine, absence retirement, and
run statistics. These writes commit together or roll back together. Different
Stores do not share the lock, even when their transport source is the same URL.
No new migration, service, dependency, transport or authentication was added.

- Absence retirement requires `snapshot_complete=True`, no quarantined records,
  and a nonempty snapshot. An empty snapshot additionally requires deliberate
  `allow_empty=True`; the scheduler never supplies it. Completeness defaults to
  false. Failed fetches, malformed envelopes, truncated mock pagination,
  duplicate identities, mismatched Store IDs and invalid records cannot authorize
  retirement. All occurrences of a duplicate identity are quarantined.
- Valid records in partial snapshots still apply, including explicit `visible`
  or `active` withdrawal. The Phase 1 conservative eligibility rule still
  applies to unknown publication flags. Malformed records preserve their previous
  projection. Retirement affects only the current Store/profile; synthetic
  rows use their previous ingestion run's source, reject cross-source key
  takeover, and leave unowned legacy rows alone until observed by a source.
- Absence retirement retains source payload/flags and adds a local revision;
  it does not fabricate an owner withdrawal. Identical eligible metadata
  reappearing after retirement also adds a revision. Synthetic delete/reactivation
  enqueue ordered delete/upsert operations in the existing outbox. Store rows
  still create **no** index operations and remain outside public v2 consumers.
- The scheduled synthetic job uses this boundary. Mock pagination checks declared
  totals, page lengths and premature termination. The legacy guessed HEDGE client
  cannot authorize absence; real Store v1 transport remains unwired.

Remaining assumptions: a caller must establish that a snapshot covers the whole
authorized Store catalogue before setting `snapshot_complete`. A syntactically
valid nonempty subset is indistinguishable from a full catalogue without that
external contract. Do not fetch outside the lock or pass a previously fetched
snapshot. Synthetic ownership depends on retaining referenced ingestion runs;
source-string changes require a deliberate ownership transition. Confirm HEDGE
visibility/`active` semantics, authorization scope and
full-response behavior with authenticated examples. Future transport must bound
fetch duration; a slow fetch holds its Store's lock and DB connection. Outbox
crash recovery, stale vector/cache rejection and public Store retrieval remain
the separate safety gate in the [baseline](integration-baseline.md).

Verification: 21 new PostgreSQL reconciliation cases cover source isolation,
partial/malformed/empty/failing snapshots, transaction rollback, publication,
identical reappearance, synthetic outbox ordering, and overlapping fetches.
They reuse the explicitly disposable `hedge_phase1_test` database and per-test
schemas. These 21 cases and the six Phase 1 persistence tests passed on isolated
PostgreSQL 16.9. The existing nine adapter tests also passed. All 239 unit tests
passed with 93.84% shared branch coverage against the 80% gate (one existing
Starlette/httpx deprecation warning). Repository Ruff and whitespace checks
passed; all six regenerated OpenAPI contracts were byte-identical. Run the
database cases with the Phase 1 persistence tests:

```sh
# HEDGE_TEST_DATABASE_URL must target a disposable database named hedge_phase1_test.
python -m pytest tests/integration/test_store_v1_persistence.py \
  tests/integration/test_catalogue_snapshot.py -q
```

The preserved demo checkout, containers, volumes and database were not used as
test resources. No live migrations or deployment were performed. These offline
checks establish reconciliation behavior, not authenticated Store acceptance.
