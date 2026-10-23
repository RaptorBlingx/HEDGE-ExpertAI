# T2 understanding and dialogue state

Local backend follow-up from the approved `c911c4b` UI baseline. The Angular
source, API contracts, E5/ranking, Store synchronization and suitability assessor
are unchanged. This is prototype engineering evidence, not a pilot KPI or a
Mid-Term Report.

## Confirmed mechanisms

- The old English Rasa corpus multiplied five topic templates per intent; it
  barely represented Store browsing, provider questions, indirect needs or
  capability follow-ups. Real HTTP parses assigned incorrect small-talk labels
  with confidence near one. Confidence alone is not a safe dialogue policy.
- Store policy therefore already overrode statistical labels for substantive
  requests. However, the one-pass interpreter did not receive those NLU hints,
  and its task text used technical source wording even where the existing
  preparation could explain it more plainly.
- Semantic capability recovery normalized a request, then assessed the original
  unfamiliar wording anyway. That defeated the translation on follow-ups. The
  task matching an operation also doubled as the App reference, although the
  subject of a question is independent of which App might meet the need.
- An unverified commercial/typed filter was returned in a response but omitted
  from persistent context. A subsequent question lost that limitation. Session
  updates merge keys, so removal also requires an explicit empty value rather
  than omitting the state.

## Changes and safeguards

`services/rasa/data/english-store.json` is the reviewed English operation corpus.
The generator retains other languages unchanged. Its existing eight boundaries
remain: discovery/listing (`search`), source inspection/capability follow-up
(`detail`), an actual comparison, modification of an earlier search (`refine`),
assistant/recovery help, greeting, explicit reset and unrelated requests.
Rasa remains stateless; application policy resolves identity and constraints.
The DIET architecture, seed, epochs, dependency pins and confidence setting are
unchanged. Regenerate and check with `scripts/generate_rasa_nlu.py`; rebuilding
the existing Rasa image trains that corpus. No new model/service dependency.

The existing structured Qwen3 4B call receives contextual NLU hints, the latest
functional need and unverified conditions. It retains technical task wording;
existing automatic plain-English preparation supplements missing vocabulary.
Bounded whole source passages supply relevant business context and qualifications
without becoming eligibility receipts. First turns retain the compact three-field,
query-first interpretation; empty state and unused reference output are omitted.
Contextual turns require a reference from the actually available bindings. The
same original-source assessor still decides suitability. This projection separates
`focus/other/first/second/both` from the selected task. Provider is an explicit
source-inspection view. There is still one call, an 80-token output budget,
the same model/context/deadline and no prose generation, review or repair loop.

Simple capability paraphrases may use the interpreted query with the existing
assessor. Negative, numeric, exclusive and other strict requests keep their
original conservative check, including compound-function coverage. Model task
selection is not a reviewed-support receipt or permission to widen scope.
Native IDs, authorization and late catalogue revision checks remain intact.

Unverified filters persist separately from explanatory topic selection. Source
reads and catalogue comparisons remain available with the relevant limitation;
they cannot become a recommendation meeting an unverified condition. An explicit
whole-clause `drop/remove/forget/clear` command can remove named pending filters;
every operand token must belong to the filter or control grammar. Negation,
unknown modifiers and compound requirements cannot silently remove conditions.
A subsequent sentence traverses normal routing. Reset/new conversation also
clears state. This grammar changes dialogue state, not capability interpretation.

Already resolved App operands survive semantic recovery, including negative
capability candidates. A comparison with the other App combines the focal App
and its peer; initial catalogue bindings survive the first semantic search.
An implicit switch to another App needs interpretation. Conflicting search/focus
instructions clarify instead of silently changing subject. Metadata operations
do not overwrite functional needs with wording such as "how do they differ".
Rasa can select help for an already unverified condition after source checks;
entity questions still require source selection rather than a generic checklist.

## Evaluation boundary

Private receipts and complete transcripts are retained under
`~/.local/share/hedge-t2-understanding/`, outside Git. Questions and hashes were
frozen before implementation: 79 regression turns, 20 exploratory multi-turn
questions and 32 separately labelled Rasa utterances. Exploratory answers informed
general evidence/context corrections; they are not the final unseen benchmark.
A further 12-turn holdout was frozen before those final corrections and is not
used for tuning. The five-turn subject-admission probe is reported separately.
The initial QA sequence contained 116 turns. Final reviewed evidence comprises
all 79 regression turns, the untouched 12-turn holdout and the five-turn probe
(96 turns). The 20 earlier exploratory questions remain diagnostic material,
not another final benchmark. Resource-interrupted replays remain separate; only
complete conversations with available inference enter quality counts. No outage
fallback is counted as a successful model assessment.

The unchanged approved Angular assets are served on loopback 8146 against an
isolated gateway/chat/expert, session PostgreSQL/Valkey and newly trained Rasa.
The stack reads the same two authorized Store Apps through the established
Discovery/E5 services and initially used the existing Qwen3 4B endpoint. After the resource incident
below, evaluation moved to a separately capped instance of the same cached model.
It does not seed,
refresh, migrate or write the existing Store databases. Only the new session
database receives migrations. Previews 8096/8106/8116/8126/8136 are preserved.

`evaluation/t2/angular-widget.cjs` captures complete rendered answers, wire
requests, SSE decisions, NLU/model provenance and submit-to-complete latency:

```bash
WIDGET_BASE_URL=http://127.0.0.1:8146 \
  node evaluation/t2/angular-widget.cjs /private/questions.json /private/result
```

Use an existing Playwright installation through `PLAYWRIGHT_MODULE_PATH` and
Chromium through `BROWSER_EXECUTABLE`. No authored App fixtures enter this UI.
Read complete answers and grade operation, relevance, false abstention,
constraint/reference retention and claim support separately. Raw Rasa accuracy
does not establish end-to-end quality; source-backed answers do not establish
large-catalogue retrieval quality. The latter remains a separate work phase.

A harness output/input filename collision in an intermediate exploratory run was
retained separately. The question source was restored against its original frozen
SHA-256; the harness now rejects collisions before starting a browser. Other
intermediate harness failures and interrupted runs are not counted as final
acceptance results. Final question hashes and complete SSE streams are checked.

## Results and operational limits

The frozen, separately labelled 32-utterance Rasa probe improved from 22/32 to
29/32 correct labels. This is a classifier probe, not independent end-to-end
accuracy. High-confidence mistakes remain, including labels on real App names.
The runtime source/identity policy must therefore continue to treat NLU as fallible.

The untouched final 12-turn holdout scored **7 Pass / 1 Partial / 4 Fail**. Its two
initial functional discoveries and the explicit post-filter-release recommendation
selected the relevant App. Two other supported requests false-abstained: settlement
benefit/penalty sharing, and selecting the market-bid App after comparison. One
provider request became a capability answer, and getting-started wording became
a capability refusal. The pricing-verification answer retained the limitation but
repeated it rather than explaining the next step clearly. The same provider
wording worked in the other App context, so this remains a contextual operation
selection problem. No invented positive capability or free-use claim was observed;
that does not excuse the incorrect negative source assertions or wrong operations.
All four pricing-session turns retained or explicitly removed the condition safely.

Those 12 turns used three prepared replies (0.696–1.127s) and nine assisted replies
(17.390–72.954s, including a 69.077s cold first request). Different CPU caps, batching,
prompt content and case mixes prevent a clean inference-speed comparison with
the original shared-worker baseline. The fast path remains important; one call
alone does not make contextual CPU inference fast or reliable.

At 20:42 UTC on 2026-10-20, shared Ollama exceeded its existing 2.734 GiB container
limit, returned HTTP 500/EOF and reloaded its worker. Its container was not restarted
or reconfigured; the OOM flag and diagnostic log are retained. This briefly affected
shared inference. All existing preview HTTP checks still passed; no existing
configuration or mount was changed, and no existing database was migrated or seeded. Subsequent evaluation waited
for normal idle unload, then used a separate 3 GiB-capped instance of the same
cached Qwen3 4B weights, read-only, with supported batch size 32 and unchanged
context/output limits. A guard stops only owned evaluation resources if host
headroom falls below 100 MiB or the shared model becomes resident. It interrupted
two long-browser replays; complete heldout results are retained and later outage
fallbacks excluded. The harness now closes Chromium between independent
conversations while retaining all turns within each conversation.

The 5.72 GiB/two-CPU VM with full swap has very little concurrent headroom. Model
measurements were approximately 2.56–2.67 GiB and 1.5 CPU cores under the isolated
cap, plus about 535 MiB for the separately trained Rasa. No model was downloaded
or changed. A full replay and operational checks do not establish large-catalogue
retrieval or ranking quality; those remain a separate phase. This understanding/
context scope is **not ready to close** while the fresh failures above remain.

### Final frozen regression and subject probe

| Set | Before Pass / Partial / Fail | After Pass / Partial / Fail |
| --- | --- | --- |
| Frozen 79 turns | 73 / 4 / 2 | 76 / 2 / 1 |
| Separate five-turn subject probe | 3 / 0 / 2 | 5 / 0 / 0 |
| Untouched 12-turn holdout | Not replayed on baseline | 7 / 1 / 4 |

Frozen requested-operation correctness was 75/79 before and 76/79 after. Both
versions correctly recommended on 8/9 supported functional requests and
false-abstained on one, but on different requests. The former shared-vocabulary
false abstention and provider/pricing-context loss are fixed. A new regression
remains: after successful discovery and comparison, a predicate-selection
question becomes another comparison and incorrectly says the documented
publishing task is unconfirmed. Recovery now supplies context that was absent
after the earlier failed search; the subsequent operation is still misclassified.
The strict comparison-criterion guard retains unconsumed operation text, so the
assessor rejects it. Loosening suitability would hide the understanding failure.
The two partials remain generic handling of unsupported mixed operations.

The diagnostic probe previously answered a capability question about one App
with a positive answer about a different App and then carried that wrong focus
into the provider follow-up. All five turns now retain the requested subject,
then correctly switch only on the explicit new discovery request. No invented
positive capability/commercial claim was observed in the selected final 96 turns.
Incorrect negative source statements remain: one in the frozen set and two in
the holdout. This distinction matters; safe-looking abstention is not evidence
that the assistant understood the request or read the source correctly.

Frozen prepared responses increased from 65 to 67, and model calls fell from
14 to 12. Prepared median was 0.384s before and 0.590s after (after range
0.217–2.497s). Assisted median was 13.163s before and 35.957s after (after range
8.396–73.678s). These are actual UI timings, not a speed-improvement claim;
CPU caps, batching, prompt content, cold starts and case mixes differ. Contextual
interpretation remains too expensive here. One Rasa request timed out to the
existing fallback, with provenance retained; its semantic answer was correct.

The 79-turn final regression is assembled from unchanged candidate code at
complete independent conversation boundaries: 28 turns before the first
headroom stop, 42 from the next replay, nine from the final confirmation. The
untouched holdout and five-turn probe are also complete. Each selected stream
contains its completion event; none uses an unavailable-model fallback. Exact
source slices, per-turn ratings, question hashes and full rendered answers are
in the private `evaluation-metrics.json` and `complete-browser-conversations.md`.
The two-App authorized catalogue projection was identical before/after.

Final verification passed 1,320 unit tests and the unchanged shared-package
branch-coverage gate (86.18%), Ruff, generated-corpus checking, JavaScript syntax
and diff checks. The added UI/backend/model/Rasa/session services were stopped
after evaluation to release RAM; their private evidence and owned volumes remain.
All 72 pre-existing containers retained their captured running state, start time
and mounts; the shared model's recorded OOM flag is the sole changed captured
field. All five preserved preview ports returned HTTP 200. No UI, dependency,
migration, synchronization, E5/ranking or authorization-policy changes are part
of this commit.
