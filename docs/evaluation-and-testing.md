# Evaluation and Testing

> **Current status:** v2 evaluation requirements are defined, but proposal KPI
> achievement is not claimed. The current evidence register is
> `docs/D3.1-Evaluation-Report.md`; the implementation/evidence boundary is in
> `docs/traceability-matrix.md`.

## Scope

This guide describes how HEDGE-ExpertAI v2 should be evaluated. It does not
turn synthetic fixtures, local tests, or internal labels into HEDGE acceptance
evidence. Evaluation reports must retain the source revision, environment,
model/artifact versions, query set, raw per-query results, and review records.

## Current evaluation assets

- The repository contains a deterministic **120-record synthetic catalogue**.
  It is a development fixture, not HEDGE App Store data.
- The repository can reproduce **200 provisional evaluation queries** and a
  multilingual Rasa NLU training asset. These labels are internal until they are
  reviewed with HEDGE.
- The live deterministic Docker profile checks transactional ingestion,
  localized filtered retrieval, versioned grounded SSE, and a real Rasa NLU
  path. It replaces LLM generation with an intentionally untrusted deterministic
  fixture so that it remains reproducible.
- Retained local evidence from 31 July 2026 records 205 passing backend tests,
  94.28% shared-core branch coverage, zero Ruff findings, and a local
  120-record ingestion/index/restore drill. This is engineering evidence, not a
  production or HEDGE sandbox acceptance result.

## Evaluation gates before KPI claims

| Area | Required evidence |
|---|---|
| Retrieval relevance | At least 50 representative queries jointly reviewed with HEDGE, with a documented relevance rubric and raw rankings. The primary result is HitRate@2; P@2, Recall@K, MRR and nDCG are reported separately. |
| Multilingual behavior | Held-out native or reviewed paraphrased queries for every required language, plus NLU results per language. Generated training examples are not independent test evidence. |
| Explanation quality | Human claim-to-evidence review confirming that explanations are grounded, preserve the ranked App ordering, and use the correct language. |
| Response time | Target-node measurements that identify the start/end event, query set, concurrent load, warm/cold state, network boundary, and time to first useful recommendation separately from full explanation completion. |
| Catalogue freshness | Authoritative source-revision/publication time and `searchable_at` evidence from the real Store contract. |
| App Store integration | Sandbox contract tests, widget embedding, authentication, App navigation, and approved Store-side security/privacy behavior. |
| Operational readiness | Target-environment security, accessibility, load/soak, monitoring, backup/restore, TLS and authorization evidence. |
| Pilot outcomes | Consented, documented pilot data for acceptance, exposure, satisfaction, discovery time, maintenance effort, or uptime claims. |

## v2 measurement flow

```text
Reviewed HEDGE query set
        |
        v
POST /api/v2/apps/search or /api/v2/chat[/stream]
        |
        +--> retain ranked results and retrieval timings
        +--> retain first useful recommendation timing
        +--> retain explanation-completion timing where applicable
        +--> compare against approved relevance labels
        `--> retain environment, catalogue revision and review evidence
```

The v2 streaming path emits `stage`, `recommendations`, `explanation_delta`,
`complete`, and `problem`. It can therefore record retrieval/first-recommendation
behavior separately from explanation generation. No report may assume which
boundary the proposal's response-time target uses until the applicable
acceptance protocol is agreed.

## Reproducible engineering checks

The following commands support local engineering verification. They do not
perform HEDGE sandbox acceptance.

```bash
make lint
make test-ci
make frontend-test
make openapi
make e2e
```

`make e2e` starts the deterministic Docker acceptance profile and runs
`scripts/e2e_smoke.sh`. It creates local development data; do not run it against
a HEDGE-managed environment.

## Reporting rule

Use **implemented** only when code and focused tests exist. Use **partial** when
material work remains. Use **pending evidence** when a feature exists but the
proposal claim is not proven. A KPI is marked passed only when its required raw
evidence is retained and reviewable.
