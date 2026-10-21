# T2 hybrid retrieval and ranking validation

Baseline `231896b` was pushed normally to Forgejo and the full remote SHA verified.
This follow-up is local only. No Rasa, Qwen, Angular, E5 weights, fusion weights,
Store synchronization, suitability policy or existing deployment changed.

## Pipeline and confirmed gap

The Store path independently retrieves PostgreSQL lexical and E5/Qdrant dense
references, resolves current publication/membership/revision/filter eligibility
against PostgreSQL, then applies weighted reciprocal-rank fusion (dense 0.55,
lexical 0.45, K=60). A five-result request uses a 40-candidate channel budget.
Rank and channel agreement never establish suitability. The expert assessor owns
source support; Qwen receipts are a separate semantic boundary.

Earlier evidence had two real Apps and a small authored catalogue, without channel
ablation, alternative recall or untouched ranking checks. This round froze 20
fictional records with overlapping capabilities, partial fits, exclusions, injection
text and an unpublished sentinel; 24 development queries and eight holdout queries
were labelled before implementation. Six queries used the two authorized Store Apps.
These are agent-authored judgments, not independent HEDGE acceptance.

The lexical baseline used `simple` on conversational English. OR retrieval rewarded
common words and missed morphological matches: “mapping” did not match “mappings”,
while “for” matched unrelated documents. English Store searches now use PostgreSQL's
English dictionary for both document and query: both forms become `map`, and `for`
is removed. Other locales and the synthetic v2 contract retain `simple`. The OR
pool, full request, filters, authorization and source checks are unchanged. No
synonyms, App-specific logic or relevance labels enter product code.

Migration `0006_store_english_lexical` adds a partial English GIN index alongside
the simple index. It changes no metadata, identities, revisions, knowledge or
vectors. Down/up was verified only in disposable databases. Small-table plans
need not choose GIN; no index speedup is claimed. A later controlled deployment
must review index-build time/write locking against the actual catalogue size.

## Baseline versus final

Positive-query averages exclude unsupported queries. MRR is truncated at five.
Inputs, source revisions, E5 and fusion parameters stayed fixed; raw rankings and
source projections were retained.

| Set / channel | HitRate@2 before → final | Recall@5 before → final | MRR@5 before → final |
| --- | --- | --- | --- |
| Frozen, lexical | 95% → 95% | 95% → 98.75% | .892 → .892 |
| Frozen, semantic | 100% → 100% | 96.25% → 96.25% | .875 → .875 |
| Frozen, hybrid | 100% → 100% | 97.5% → 98.75% | .900 → .875 |
| Holdout, lexical | 50% → 100% | 66.67% → 100% | .542 → .833 |
| Holdout, semantic | 100% → 100% | 100% → 100% | 1.000 → 1.000 |
| Holdout, hybrid | 100% → 100% | 100% → 100% | .833 → 1.000 |
| Real Apps, hybrid | 100% → 100% | 100% → 100% | 1.000 → 1.000 |

Frozen has 20 positive/four unsupported queries; holdout six/two; real five/one.
One relevant App remains outside five for the broad mapping request; none are
missed at five on holdout or real positives.

Hybrid false candidates@2 were **21/48 → 22/48** on frozen, **8/16 → 8/16** on
holdout and **7/12 → 7/12** on real. These are full-request-irrelevant slots, not
false recommendations. All four synthetic development negatives and both holdout
negatives still retrieve candidates. Dense retrieval returns nearby Apps at this
size; abstention belongs to suitability. No arbitrary similarity threshold was
fitted to these few examples.

Representative actual rankings (Apps in this table are fictional):

| Request | Baseline hybrid → final hybrid | Assessment |
| --- | --- | --- |
| “Find applications for mapping data.” | MeaningHub, MaintenanceDocs, MeterScope, CommandCard, ModelCommons → FlowMapper, MeaningHub, MaintenanceDocs, CommandCard, ModelCommons | One alternative recovered; PayloadPipe still missing at five. |
| “We want to estimate how much electricity buildings will need tomorrow.” | LoadAhead, MeterScope, PriceLens → PriceLens, LoadAhead, MeterScope | Regression: demand forecaster moves 1 → 2; E5 itself prefers the price forecaster. |
| “We need an early warning system for worn bearings in a wind generator.” | MaintenanceDocs, TurbineWatch → TurbineWatch, MaintenanceDocs | Untouched holdout improves 2 → 1; manuals remain irrelevant. |
| “Combine flexibility bids, submit them to a live market and calculate settlement allocations.” | SettlementDesk, BidRelay → SettlementDesk, BidRelay | The complete fit still ranks second behind a settlement-only partial fit. |

## Evidence, suitability and integration

Source inspection confirmed the missing mapping alternatives document payload
mappings: this is ranking loss, not absent evidence. SchemaCheck lacks conversion,
LedgerPlan's automatic settlement is planned, and LoopLab's combination is limited
to simulation. Both channels can rank partial/qualified Apps highly. This sample
does not justify fusion retuning; rank-only fusion does not assess full requirements
or negation.

The prepared assessor promoted **zero** candidates across the natural synthetic
development/holdout queries, with zero false positive promotions. Its conservative
lexical boundary remains a recommendation limitation, not a retrieval failure or
proof of semantic suitability. Qwen/Rasa were not invoked or evaluated. Two of
five real positive query types received prepared support. Broader natural-language
suitability acceptance remains open; retrieval scores cannot close it.

Actual Discovery and Expert HTTP calls used pinned E5 and copied authorized Store
metadata, without an in-process adapter or generation. Six Discovery calls ranked
the relevant App first for all five supported needs at 0.092–0.167 s in the initial
warm smoke. Expert recommended EdgeConnect for `settlement`, Semantic Treehouse
for `publish shared data models` and a requested quoted native name; it abstained
for `weather forecasting`. Publisher filtering returned only TNO's App; an
unsupported taxonomy filter returned none. These are service timings, not widget
latency or load percentiles.

The authorized observation was read from the synchronized projection without
triggering authentication or sync. Initial ablations used distinct Store scopes
and Qdrant collections in a disposable database. For final isolation verification,
the real copy was moved to a separate disposable database and removed from the
authored database; authored rankings were checked unchanged and HTTP smoke repeated
against the separate real database. No fixture entered a live Store/demo database,
collection or response.

The final separated-database HTTP smoke passed at 0.117–0.152 s for Discovery and
0.135–0.164 s for Expert. During setup, overlapping E5 HTTP worker startup hit
the owned evaluator's 1,100 MiB limit and killed one owned process. Owned workers
were stopped and a single worker completed the final smoke. Shared workers were
never called or restarted; the incident is retained in private resource evidence.
Run E5 driver/HTTP workers sequentially on this VM, not simultaneously.

The full unit suite ran once: **1,359 passed**, shared branch coverage **88.14%**.
Ruff, whitespace, staged secret scanning, frozen-input hashes, migration down/up,
source revision preservation and HTTP checks passed. Existing previews/services
and source payloads were checked after stopping only owned evaluation services.
No model inference, browser replay, further push, merge, tag, Jira change or
production migration/deployment occurred.

## Prototype review boundary

Hybrid discovery is ready for a **bounded prototype review**, with the ranking
regression and partial-fit limitations above. It is not universally better than
E5 alone and does not demonstrate complete recommendation correctness. Remaining
work includes larger sparse/long-document catalogues, filtered candidate starvation
beyond the 160-vector scan, complete-fit ranking/suitability and jointly labelled
HEDGE sandbox evaluation. E5 uses one 512-token passage per App; long-README coverage
was not established. No scalability, throughput, multilingual or formal HEDGE KPI
acceptance is claimed from 19 eligible fixtures and two real Apps.

Reproduction: [evaluation guide](../evaluation/retrieval/README.md). Protected raw
rankings, full evidence, frozen hashes, HTTP responses and preservation checks
remain outside Git under `~/.local/share/hedge-t2-retrieval/`.
