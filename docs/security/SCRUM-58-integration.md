# SCRUM-58 integration evidence and temporary npm exception

Prepared 19 October 2026. Status: verified integration candidate; maintainer
acceptance and server CI/protection verification remain pending. This document
does not assert that the target integration branch has been updated.

## Exact scope and prior review

- Target: `feat/hedge-store-v1-integration`, fetched from Forgejo at
  `eddb1794d9ddc74db01c05928d69b20eb6690d99`.
- Source: `feat/SCRUM-39-recommendation-suitability` at
  `c881c6d1f7322b51372262d61c99c20ab488dc15`.
- Candidate: `feat/SCRUM-58-suitability-integration`. Merge commit
  `39d83c7d0e9c58ad2738191c4665f294e96faef5` has both named heads as parents.
  Its tree is byte-identical to the source tree
  `350ed182a328f2297590b6e1e753a824ea0bc329`; no conflicts or manual resolutions.
- Exactly four source commits: `bd8de29`, `3e276bc`, `ec6503f`, `c881c6d`.
  No performance, experimental, browser-metadata or later Store branches included.
- [SCRUM-39](https://aartimuhendislik.atlassian.net/browse/SCRUM-39) is Done for
  engineering delivery. Its retained description records conditional product GO,
  447 focused checks and a pending maintainer npm-gate decision, followed by
  independent Tolga QA on the integrated SHA. Its one comment confirms that it
  was published but awaiting integration. Neither record is final merge approval.
  Detailed implementation evidence: [suitability notes](../recommendation-suitability.md).

## Revalidated vulnerability evidence

Node 20.19.4 / npm 10.8.2, registry-backed full and `--omit=dev` audits on the
fetched baseline, fetched source and candidate: identical findings. Baseline and
source used clean manifest-only directories with `--package-lock-only`; candidate
also used `npm ci` followed by installed-tree audits. Both manifest files are
unchanged. Every affected lockfile node has `dev: true`.

| Audit | Baseline | Source | Candidate |
| --- | --- | --- | --- |
| Full, affected package entries | 8 high / 4 moderate | 8 high / 4 moderate | 8 high / 4 moderate |
| Production only, all severities | 0 | 0 | 0 |
| Original `npm audit --audit-level=high` outcome | fails | fails | fails |

All three raw full JSON reports have SHA-256
`2d8562677ba4001a98e8961dfa96d91579f1eb7367ea00c39736809f130f3600`;
production reports have SHA-256
`de93c813ceee1296e87118395fdca9241cfdba9f98645b944e85203fad5b24e1`.
The [exception snapshot](SCRUM-58-npm-exception.json) retains exact advisory
objects, affected paths, severities and both manifest hashes, not just counts.

The former npm gate was accurately reporting inherited tooling vulnerabilities;
it was not a test bug. The explicit policy change accepts this precise graph
temporarily; it does not relabel the original audit as passing or remove findings.

## Exception limits

The task owner explicitly authorized an unchanged development-only exception in
the SCRUM-58 request and follow-up. It applies only to the named candidate and
target integration branches and expires **26 October 2026 00:00 UTC / 03:00
Istanbul**, without automatic renewal. Required maintainer approval is still
required before target integration. Remediation is tracked independently in
[SCRUM-60](https://aartimuhendislik.atlassian.net/browse/SCRUM-60).

`scripts/check_npm_audit.mjs` runs full and production audits and retains their raw
JSON and stderr in `frontend/npm-audit-reports/` (uploaded by CI even on failure).
The gate requires zero production findings of any severity. It rejects changed
manifests, changed advisory objects, non-development affected paths, unrelated
branches, expired exceptions, malformed reports and audit command failures.
It prints an explicit exception result, never a clean-audit claim.

The affected APIs are build/test tooling; prior source review found no chat or
Store input fed into them. Development/CI exposure remains a risk, which is why
the exception has exact graph limits and a short deadline. Python dependency,
licence, secret, SBOM and Grype checks remain intact. A separate scanner failure
must be reviewed under its own policy; this exception does not override it.

## Fresh candidate verification

- Python 3.11.15 disposable runner, pinned repository dependency locks: **1,058
  unit tests passed**, shared branch coverage **93.58%** (80% required).
- **170 integration tests passed, no skips**, on newly created internal-network
  PostgreSQL 16.9, Qdrant 1.18.2 and Valkey 8.1.3, ephemeral storage, no host ports.
  Fixtures exercised persistence/retrieval, suitability, native identity,
  withdrawal/stale vectors, dialogue and recommendation pipeline. No live Store,
  private snapshots or live model needed. Disposable resources removed afterward.
- Ruff passed for shared/services/tests/scripts/evaluation/database. Six OpenAPI
  exports matched tracked files. Catalogue, NLU and evaluation generation checks
  passed (120 / 1,600 / 200 respectively).
- `npm ci`, licence policy (332 packages), **25 frontend/widget tests**,
  TypeScript/Vite production build and widget JavaScript syntax check passed.
- Security exception regression checks cover accepted baseline, clean audit,
  production findings, expiry, branch scope, lock changes, new advisories,
  severity escalation, runtime paths, error payloads and missing/inconsistent data.
  Fresh gate execution explicitly accepted the temporary exception and reported
  zero production findings.

Local raw audit/JUnit/coverage logs are retained under
`/tmp/hedge-scrum58-audit/` and `/tmp/hedge-scrum58-evidence/` for this run.
These temporary paths are not durable CI artifacts. Full remote CI, image builds,
Python audits, licence inventory, history secret scanning, SBOM/Grype and full
production-path E2E were not newly certified by these local checks. No production
deployment or preserved demo operations were performed.

## Remaining acceptance

Authenticated Git fetch/push is available. Private Forgejo web/API reads return
404; no configured Forgejo CLI/API credential is available. Before submission,
Git advertised no existing pull-request refs. Consequently server protection settings, current
review approvals and CI statuses cannot be verified through the available access.
Do not infer approval from permission to push or bypass protection with a direct
target push. Submit this candidate for maintainer review; verify required checks
and record independent QA against its pinned SHA before closing
[SCRUM-58](https://aartimuhendislik.atlassian.net/browse/SCRUM-58).

The candidate was published using authenticated Git. Forgejo's AGit submission to
`refs/for/feat/hedge-store-v1-integration` returned
[PR #1](https://code.arti.ac/europe/HEDGE-IoT/pulls/1); its advertised
`refs/pull/1/head` matched the published candidate `46f8c9e`. This is publication
evidence, not proof of maintainer approval or successful remote CI. The target
remained at `eddb179` after submission.
