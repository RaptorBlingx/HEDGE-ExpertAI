# Accepted fast Store integration

On 19 October 2026 the sole HEDGE maintainer accepted the implementation and
English widget experience at `perf/prepared-store-discovery` / `e69e861` and
authorized integration and publication to Forgejo, without deployment or Jira
changes. The authorized workflow is an ordinary non-forced Git update, subject to
server receive checks; no protection or approval setting is changed.

## Reconciliation

Authenticated fetch and `ls-remote` revalidated the target
`feat/hedge-store-v1-integration` at
`0a02b5ad2da74222fd85b10b6a3b2c998025db9d`, rather than assuming the dated handoff
remained current. A clean three-way merge of `e69e861` preserves both histories.
Its application/shared/widget/database tree matches the verified merge simulation.
SCRUM-39 remains in target ancestry and is not replayed. `de2fc1b` composes the
Store prerequisites once; all later performance, M2M, knowledge-preparation,
conversation and finalization commits are ancestors of the integrated result.
No separate experimental branch is included.

[The detailed handoff](integration-handoff-prepared-store.md) remains authoritative
for prerequisite/service/configuration boundaries and migrations 0004/0005. The
[frontend dependency policy](security/frontend-dependency-policy.md) supersedes
its temporary npm exception. Compatible development dependency updates fix six
reported findings; exact remaining development-only risks are explicitly accepted
without calendar expiry or dependence on the cancelled remediation task. No task
was created or updated. Production versions are unchanged.

The CI workflow and ignore/security/history records are retained. The npm checker
and its negative tests are deliberately updated; raw findings are retained and
reported, not falsified or suppressed. Other scanners and protections are unchanged.

## Verification

- Integrated backend: 1,266 unit tests, 87.41% shared branch coverage; 149 isolated
  integration checks, including populated 0003 upgrade to 0004/0005, repeat
  application, derived rebuild and disposable rollback without source-data loss.
- Ruff, all six OpenAPI exports and deterministic catalogue/NLU/evaluation asset
  checks pass. Development/production Compose configurations validate without
  starting containers.
- Updated lockfile: clean `npm ci`, 25 frontend tests, production build and licence
  policy pass. All 12 audit policy tests pass. Real audit gate reports 5 high and
  1 moderate accepted development-only findings, zero production findings.
- The accepted source's complete English browser conversations used two real
  synchronized authorized Apps, native IDs, Rasa/E5 and actual HTTP/SSE. All 16
  turns completed in 128–340 ms (median 285 ms). Application/widget code in this
  integration matches that evaluated source; follow-up changes affect dependency
  tooling/policy and documentation. No deployed workspace was restarted for this
  integration. A local validation adapter is not proof of a production mesh.

Local receipts are retained under `/tmp/hedge-publish-evidence` and copied to a
private durable final evidence directory. The publication receipt records the
actual final SHA and re-fetched target. Private web/API access returns 404 with
the available access; Git submission does not prove that remote CI ran or passed.
Remote results must be reported as unavailable unless separately observed.

## Controlled private testing

The code is suitable for a controlled, isolated private testing deployment after
maintainer review of the published result and any available remote CI. This is
not production acceptance. Keep all existing deployments untouched. Use an
explicitly selected private-test database and service names/ports/volumes, never
the preserved `hedge` demo resources. Before later authorized activation, back up
that database and run the existing migration runner for additive 0004 and 0005;
retain native source records/revisions/history/outbox. Neither live database
migration nor any deployment is part of this integration.

Provision backend-only `HEDGE_STORE_ISSUER`, `HEDGE_STORE_CLIENT_ID` and an owned
mode-0600 `HEDGE_STORE_CLIENT_SECRET_FILE` via a read-only mount, with the approved
Store ID/API origin. Do not also set the legacy token file. Preserve incoming-user
authentication, public-visibility gates and disabled-by-default public indexing.
Validate real authentication/synchronization and widget continuity in the isolated
environment before broadening exposure. Two authorized Apps do not prove global
catalogue completeness, larger-real-corpus quality or freshness KPIs. Native UI,
full service-mesh behavior and production rollout remain separate acceptance work.
