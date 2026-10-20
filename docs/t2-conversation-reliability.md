# Store conversation reliability follow-up

Based on `085f846`, on `feat/t2-quality-improvements`. The preserved prototype
checkpoint and the private demonstrations on 8096, 8106 and 8116 are unchanged.

## Observed causes

The real widget baseline reproduced failures across gateway → Rasa/chat → Expert
→ Discovery, using the two synchronized Store Apps and Qwen3 4B. These were not
retrieval outages or missing source metadata:

- Browsing had several competing recognizers. Dialogue normalization recognized
  a compound listing, but semantic-recovery admission checked the original text
  again. The interpreter has no browsing mode; it turned that valid listing into
  discovery, sometimes recommending one App instead of describing the catalogue.
  The browsing grammar also treated terminal punctuation differently from other
  conversational controls. Rasa's statistical label did not resolve this conflict.
- A resolved inspection was still sent to the model. A purpose request could
  become a capability query, causing suitability to reject conversational text
  or an opaque UUID as if it were a functional requirement. An inspection could
  consequently lose the reference needed by the next provider question.
- The widget serialized a card's native App ID into its visible message. That
  conflated presentation, identity and operation, requiring an interpreter to
  rediscover information the UI already had.

## Changes and boundaries

- One token-based, whole-utterance catalogue grammar is shared by routing and
  execution. It composes listing with purpose inspection of each entry. Casing,
  whitespace and punctuation do not add functional terms. Extra requirements,
  filters and unknown operations prevent unrestricted browsing; they continue to
  discovery/interpretation. The old exact compound-question normalization is removed.
- Resolved inspection commands reuse the existing source-field read and prepared
  composition paths. The complete operand must resolve to a current native ID,
  unique name or dialogue reference. An arbitrary `explain …` prefix cannot
  discard a requirement. Purpose, provider and comparison bindings remain distinct.
  Overviews preserve the existing provider information.
- Optional `ChatRequestV2.app_action` carries `{type: "inspect", store_id, app_id}`.
  The visible card action uses the App name. The backend resolves the exact opaque,
  case-sensitive pair in the authorized catalogue. Stale/out-of-scope actions do
  not bind to another App; unknown fields/operations are rejected. Existing filters
  and the late catalogue-revision check still apply. Actions require Store mode
  and do not depend on the planner setting. OpenAPI exports document the addition.
- Catalogue composition describes every displayed entry using current prepared
  purpose evidence, without treating catalogue wording as recommendation terms.
  Browsing/inspection decisions explicitly remain non-recommendations. Functional
  requests still use the existing suitability assessor and retrieval architecture.

There is no model/prompt replacement, new service, App-specific answer, synonym
expansion, ingestion change, migration or reindex. Rasa, E5, authorized Store
synchronization and Qwen3 4B's constrained one-pass interpretation remain intact.

## Reproducible evaluation boundary

The source archive, question files and their hashes were frozen before application
changes. A disposable loopback-only 8126 stack owns its chat database/cache and
application processes. It reuses the existing Rasa, E5/Discovery and Qwen endpoint;
it never refreshes, seeds, migrates or writes the existing Store databases.
Resource headroom was checked before inference; no second model was loaded.

The frozen checklist contains 36 turns: catalogue variations and compounds,
constrained discovery, names/native IDs, real card clicks, provider/purpose/access/
pricing questions, recommendations, comparisons, simplification, topic changes,
supported/unsupported capabilities and no-match recovery. A separate 15-turn set
is held out from debugging and replayed on both versions, without tuning to its
results. These are engineering judgments, not blinded independent acceptance or
proposal KPIs. Complete English answers are read, not graded by keyword hits.

Pass means the requested operation, subject, source facts and displayed Apps are
correct and useful. Partial includes shallow comparisons or safe but unhelpful
no-match answers. Fail includes false abstention, wrong operation, wrong identity
or unsupported assertions. Categorize failures by the responsible pipeline stage;
report prepared/model-assisted latencies and call counts separately.

`evaluation/t2/widget.cjs` accepts strings and `{click: "displayed App name"}`
questions. It records the actual wire request, visible user text, complete answer,
SSE decisions, Rasa results, model provenance and timings. It respects the normal
chat rate limit and closes Chromium on failure. For example:

```bash
WIDGET_BASE_URL=http://127.0.0.1:8126 \
  node evaluation/t2/widget.cjs /private/questions.json /private/output-prefix
```

Set `PLAYWRIGHT_MODULE_PATH` and `BROWSER_EXECUTABLE` for an existing private
Playwright/Chromium installation if needed. Inspect error files and complete SSE
events before counting answers. Each card-click sequence must first display its
card; a failed inspection can legitimately remove the previous side pane.

Raw Store transcripts, source snapshots, runtime configuration, intermediate
failures and receipts remain outside Git under
`~/.local/share/hedge-t2-reliability/`. An initial baseline harness run stopped
because a failed inspection removed the next card; it is retained separately.
Listing preconditions were corrected and the full baseline replayed before
replacing its frozen source. Synthetic 102-entry catalogue and duplicate/unnamed
identity checks establish code contracts only, not live recommendation quality.

## Recorded results

Manual review of complete widget conversations, with partial answers kept visible:

| Set | Before: Pass / Partial / Fail | After: Pass / Partial / Fail |
| --- | --- | --- |
| Frozen 36 turns | 24 / 3 / 9 | 33 / 3 / 0 |
| Held-out 15 turns | 9 / 2 / 4 | 13 / 1 / 1 |

The remaining held-out failure is nested listing plus an indirect purpose clause.
The partials are shallow comparisons and a generic safe response to a free-only
filter. No unsupported capability or commercial claim was observed. The four
functional-discovery requests and the supported settlement follow-up selected
the relevant App on both versions; they do not establish large-catalogue ranking
quality. Source evidence, not the model's task selection, still decides suitability.

On the frozen set, prepared turns increased from 20 to 31; their median was
0.350s before and 0.361s after (after range 0.169–0.683s). Model calls fell from
16 to 5. Remaining assisted turns took 9.633–14.920s, median 13.563s; their
changed case mix is not evidence of faster model inference. On held-out turns,
calls fell from 9 to 4; prepared median was 0.332s, assisted range 7.819–11.456s.
The same CPU-only Qwen3 4B instance used approximately 2.62 GiB; no second model
or E5 process was loaded. All final browser runs had complete SSE events and no
browser/HTTP errors. Three additional real gateway checks rejected out-of-scope
targets, unknown action types and unsupported filters without a recommendation.

The final source passed 1,310 unit tests and the unchanged 80% shared branch
coverage gate (86.02%), Ruff and JavaScript syntax checks. Those are supporting
checks, not the product acceptance result. Full transcripts, per-turn assessments,
latencies, stage traces and source hashes are in the private evidence directory.

## Remaining design limits

The catalogue and inspection grammars are deliberately bounded. Nested compound
requests and unfamiliar operations can still reach an interpreter with no catalogue
mode. Comparisons can select a narrow prepared task rather than a useful overall
distinction. Conservative unsupported-filter handling can be safe but generic.
Browsing is capped at five entries and has no conversational pagination; the two
real Apps do not validate larger-catalogue coverage. Qwen-assisted turns retain
CPU inference cost and uncertainty; this is not a complete T2 acceptance claim.
