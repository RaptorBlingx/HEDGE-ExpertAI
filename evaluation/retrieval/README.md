# Controlled hybrid retrieval evaluation

`catalogue.json` contains **20 fictional Apps**, one unpublished. `frozen.json`
has 24 queries (20 positive, four unsupported); `holdout.json` has eight (six
positive, two unsupported). Questions, catalogue and agent-authored relevance
judgments were frozen before the lexical change. These are engineering inputs,
not HEDGE-approved sandbox labels, real products or proposal KPI evidence.
Judgments require the whole request; a partial fit can be a retrieved candidate
without being a valid recommendation. Broad requests have several relevant Apps.
Keep private real observations outside Git.

The runner uses actual PostgreSQL, pinned E5 query/passage embeddings, Qdrant,
authoritative hydration, reciprocal-rank fusion and the prepared source assessor.
It captures complete projections/evidence and channel rankings. All three modes
use the same queries, eligible catalogue, filters, candidate budget and cutoff.
No mock vectors or language model judgments are used. Store caching is already
disabled by the product.

HitRate@2, macro Recall@5 and MRR@5 use **positive queries only**. Unsupported
queries are separate. False candidates@2 counts returned slots whose App does
not satisfy the full label, including unsupported queries; this does not mean
the product recommended them. Prepared suitability uses existing normalization
and source assessment, without Qwen support receipts. It is a component check,
not an end-to-end conversation score.

## Reproduction

Check resources and image availability first. This VM has the pinned CPU E5
evaluation image prepared by the existing
[`store-v1-playground.sh`](../../scripts/store-v1-playground.sh) model-image flow:
`sha256:e02493fccbbf67c15c6abf52e25695963795cb9f588f99b7e1fd75db475b41cb`.
It contains `/opt/e5-model`, multilingual-e5-small revision
`614241f622f53c4eeff9890bdc4f31cfecc418b3`. Other hosts must prepare the same
artifact; this runner never downloads or substitutes models.

From the repository root, choose a **new** Compose project and a mode-0700 private
output directory outside Git. Do not reuse any demo project, database or network.
After exporting `RETRIEVAL_EVIDENCE_DIR` and `RETRIEVAL_EVAL_IMAGE`:

```bash
docker compose --env-file /dev/null -p expertai-retrieval-review -f evaluation/retrieval/compose.yml up -d
docker compose --env-file /dev/null -p expertai-retrieval-review -f evaluation/retrieval/compose.yml exec -T retrieval-db pg_isready -U evaluator -d hedge_retrieval_eval
docker compose --env-file /dev/null -p expertai-retrieval-review -f evaluation/retrieval/compose.yml exec -T evaluator python database/migrate.py
docker compose --env-file /dev/null -p expertai-retrieval-review -f evaluation/retrieval/compose.yml exec -T evaluator python evaluation/retrieval/evaluate.py --seed --catalogue evaluation/retrieval/catalogue.json --queries evaluation/retrieval/frozen.json --store-id t2-retrieval-authored --output /evidence/frozen.json
```

Wait for database readiness before migration. Seed rejects a nonempty database.
The internal network has no host ports, external networks or Store credentials.
The evaluator is capped at 1,100 MiB/1.25 CPU without swap; it sleeps until invoked.
UID/GID defaults to 1000; override the Compose variables if needed to write output.
Never publish the evidence directory.
Run one E5 process at a time; stop a CLI/HTTP worker before starting the next.

Run the holdout once after decisions are fixed by replacing `--queries` and
`--output`, without `--seed`. To compare revisions, retain identical inputs,
embedding artifact and the exact source SHA. Lexical-only calls the same production
SQL as hybrid; it is not a separate search implementation.

Real observation smoke checks use the distinct disposable database
`hedge_retrieval_real`, native Store ID and derived collection. Populate it only
with an authorized saved observation through the same seed/reconciler. Never mix
fixtures into it or write to a Store deployment. Integration checks must also call
the actual Discovery/Expert HTTP routes; this CLI does not test Angular or HTTP.

Stop only this evaluation project afterwards. Keep evidence and volumes for review;
later deletion must explicitly target this disposable project.

Results: [engineering handoff](../../docs/t2-hybrid-retrieval.md).
