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

## Executable evaluator semantics

The evaluation-correctness remediation reproduces Astra finding 7 against
`4a9e964`: invented savings/certification claims passed the text heuristic,
one correct search plus nine timeouts reported 100% HitRate@2, and a stream
containing only a 503 `problem` event was counted as successful. Focused HTTP
mocks exercise the evaluator functions and its executable `__main__` path;
they do not access the preserved demo or establish live-model quality.

- Every attempted query is retained in `per_query`. `evaluated` counts valid
  successful responses; `failed` accounts for HTTP errors, timeouts, malformed
  responses, and failed/incomplete streams. All attempts remain in retrieval
  means, confidence intervals, and category denominators; failures score zero.
- Relevance uses exact `expected_apps` IDs against returned App IDs in rank
  order. A matching title or fluent explanation cannot substitute for identity.
  Missing/invalid/duplicate response IDs fail validation; invalid query labels
  fail before requests. Empty expected lists are allowed for no-match probes:
  they cannot earn a positive HitRate@2 and must be interpreted separately from
  positive retrieval tasks when constructing an acceptance protocol.
- Explanation length and fallback detection are formatting diagnostics only.
  `explanation_accuracy` is `null` with status `unassessed` for chat and stream.
  The evaluator has no human-review input path; factual/contextual accuracy
  requires a separate reviewed claim-to-source record for the actual output.
- SSE succeeds only on a valid terminal `complete` event. `problem`, malformed
  data, timeout, or EOF without `complete` fails, even after partial text or Apps.
  Partial output remains in per-query evidence but earns no retrieval credit.
  Multiline SSE data and heartbeat comments are supported.
- First explanation text and first nonempty App-result timings are observed
  independently. A first App does not establish relevance. Aggregate TTFT/TTFA
  uses successful streams with the corresponding event, reports sample counts,
  and leaves absent measurements `null`; completion time is never substituted.

The [proposal](proposals/HEDGE-IoT-OC1-Proposal-HedgeExpertAI.md) specifies
**average response time <5 s** in objective 2 and **median response/query
time <5 s** in its impact and task targets. The evaluator reports arithmetic
mean, median, and nearest-rank P95 separately. Timing starts immediately before
the request and ends after the complete JSON response is read/validated, or
after terminal SSE `complete`; on failure it ends at the observed failure.
All attempts contribute observed durations. Timeout durations are censored
failure observations, not successful responses; a low mean never proves a
timing target when requests fail. First-output timing is not full completion.
These are client-observed API timings, excluding UI/user think time. The target
host, network boundary, load, warm/cold state, and accepted end event still need
agreement before either proposal target can be claimed.

Run only against an explicitly chosen evaluation endpoint, never the frozen
demo. `--output-json /absolute/path/results.json` optionally retains aggregate
metrics and per-attempt IDs, status, errors, scores, and observed timings. Keep
reports containing private IDs/query identifiers outside Git. The executable
returns 1 if any selected mode has a failed request or exploratory HitRate@2
below 70%; 0 means those engineering checks passed, while proposal acceptance
and explanation accuracy remain unassessed. Invalid input/arguments return 2.
No analytics endpoint is fetched by default. The legacy `--report-feedback`
option is outside this remediation; it is not pilot-adoption acceptance evidence.
Returned-App coverage is a retrieval diagnostic, not qualified visits.

Focused offline verification:

```bash
python3 -m pytest tests/unit/test_evaluation_correctness.py
```

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
