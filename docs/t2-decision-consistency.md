# T2 decision consistency

Engineering follow-up to `9e7bf78`, on `feat/t2-backend-completion`.
Subsequent bounded work from checkpoint `2cde320`: [operation/reference handoff](t2-operation-reference.md).
The approved Angular frontend, Store synchronization, E5/ranking algorithm, model weights,
authorization boundary and existing previews are unchanged.

## Decision boundaries

- The pinned native Ollama path was observed emitting schema properties in
  alphabetical order, regardless of Python declaration order. The original wire
  order was `mode, query, reference, task`. The private schema now uses
  `operation, reference, source_function, unmatched_requirements`, whose declared
  and alphabetical orders agree. See
  [Ollama issue 18717](https://github.com/ollama/ollama/issues/18717).
- A redundant numeric task classification could replace a correct stated need
  with another App's canonical function. Interpretation now selects a descriptive
  source-function key and separately retains user-requested operations or
  restrictions that function does not cover. There are no competing whole-need
  outputs. The key begins with source vocabulary, rather than an opaque number
  or a generic App-name prefix; its full source text remains the evidence.
- Retrieval ranked the correct App first for both pooling bids and establishing
  a common vocabulary, but interpretation discarded that order for native-ID
  order. Required references remain in the bounded scope; existing retrieval
  relevance now determines its order. No ranking algorithm or index is replaced.
- Prepared purposes, readable functions and bounded source context remain input.
  Whole native feature declarations enter the same vocabulary only after passing
  the existing assessor. Unadmitted labels are not selectable functions. The
  latest question follows context; misleading Rasa hints and raw earlier
  questions are omitted.
- Full functional interpretation retains one constrained 80-token output budget; there is no writer,
  reviewer or repair call. Source-function selection avoids the former
  80-character paraphrase bound. Unmatched requirements are separately bounded
  to 160 characters each. Missing functional meaning falls back to checking the
  original request, never to approving an arbitrary available function.
- Already parsed source-field operations remain authoritative. If identity alone
  is unresolved, a reference-only constrained call (24 output tokens) resolves
  focus/peer/ordinal/set; the existing authorized source reader supplies the
  actual value. Ambiguous identities and constrained native targets remain
  terminal. Provider attribution is metadata rather than a selectable function.
- Parsed comparisons constrain recovery to the comparison operation; copied
  operation scaffolding cannot become a capability criterion. Broad catalogue
  browsing is an explicit interpretation operation; functional or strict
  requirements cannot be silently converted to that listing.
- Native names/IDs and validated conversational references determine scope.
  Discovery NLU can corroborate an unbound discovery route; absence of a closed
  lexical reference alone cannot invalidate a semantic singular reference.
  Selection from an explicitly displayed set checks the bound set.
- Function selection never grants a recommendation. The final subject, every
  unmatched requirement, retained conditions and fresh authorized source still
  undergo the existing application-owned decision checks. Original-request
  guards for lost conjunctions, restrictions and numbers remain active.
- Provider/access/pricing operations survive capability fallback. Rasa can
  corroborate recovery only after an unsuccessful search for the unchanged need;
  it cannot replace a source operation or veto a positive suitability decision.
- Pending filters forward their retained requirement, not only the field name,
  so a follow-up about "that condition" has the original value available.
- An unsuccessful discovery clears its result set while retaining the discussed
  App if it remains authorized. Failure to find a new match cannot erase the
  identity needed by a later provider, purpose or access question.
- A canonical comparison need is retained through presentation. A copied
  comparison command cannot replace an established need. Discovery explains its
  assessed need; detail follow-ups can select a more specific source passage.
- A complete, unqualified native `featureList` label remains evidence even when
  neutral surrounding prose is unresolved. Existing qualification, negative,
  original-request, revision and visibility guards remain active. Uncertainty
  does not establish that a feature is absent from the source.

`generation.interpretation` distinguishes the proposed operation from the
effective operation and records the function, unmatched requirements and native
identity order supplied to interpretation. `generation.routing` records subject/candidate identities,
the decision query and strict-request handling. Per-turn review must distinguish
wrong interpretation, wrong scope, retrieval miss, source decision and final
answer quality; a correct App name alone does not establish a correct pipeline.

## Verification protocol

The 79-turn regression and previous 12-turn holdout are known sets. A new 20-turn
holdout was authored and hashed before implementation changes, with source-based
expectations recorded before viewing its answers. No authored catalogue was
served: browser evaluation uses the two authorized synchronized Store Apps.
Complete rendered answers, source snapshots, per-turn ratings and pipeline
records remain private runtime evidence outside Git.

The preserved VM has approximately 5.72 GiB RAM and two CPUs, with little swap
headroom. Evaluation uses an owned 3 GiB/1.5-CPU Qwen3 4B container with cached
read-only weights and an owned Rasa worker. Their residency is serialized: real
Rasa HTTP parsing completes before the owned model runs; stateless Rasa is then
reloaded between assisted turns. Angular, gateway, chat, expert, discovery and
session persistence use real service boundaries throughout. No replayed model or
NLU response is served to the widget.

This protocol preserves shared inference and running previews. Ownership and
headroom guards stop only owned evaluation resources. Assisted request times
include cold model loading and in-request worker scheduling; between-turn Rasa
readiness is recorded separately. The final private deadline is 150 seconds,
after an earlier diagnostic 90-second cold-prefill run timed out. That failed
diagnostic is retained separately and is not successful verification. These measurements
are not a warm-serving or concurrency benchmark, and no existing deployment
configuration was changed.

A further independent 12-turn holdout was authored before the final boundary
changes. The initial 20-turn results are retained as development evidence; any
repeat is explicitly a retest. Final results must use one frozen source manifest,
including inference errors and safe fallbacks. Rewording an incorrect negative
claim as uncertainty is not counted as fixing a false abstention.

## Engineering wrap-up and remaining limits

The final local code is candidate T. The user requested wrap-up during its
four-turn operations session; that session completed normally. Queued broad
regression and retest suites were cancelled before starting. Complete private
transcripts and pipeline ratings are in
`~/.local/share/hedge-t2-decisions/complete-browser-conversations.md`,
`evaluation-metrics.json` and `pipeline-review.json`. Runtime data and credentials
are excluded from Git. Earlier snapshots are explicitly distinguished:

| Completed real-widget set | Code snapshot | Pass / Partial / Fail |
| --- | --- | --- |
| Frozen 79-turn regression | R, before final boundary changes | 76 / 3 / 0 |
| Known previous 12-turn holdout | S, before final boundary changes | 6 / 1 / 5 |
| First independent 20-turn holdout, used to inform final fixes | S | 9 / 2 / 9 |
| Final independent context holdout, 8 turns | T | 5 / 1 / 2 |
| Final independent operations holdout, 4 turns | T | 2 / 0 / 2 |

These are not pooled into a final regression score. Compared with `9e7bf78`, R
fixed the publishing-selection false abstention and improved an unsupported-search
response, but regressed singular scope (turn 51) and pricing-verification help
(turn 76). S fixed market-bid selection in the known holdout, but regressed its
provider and comparison turns (6 and 7). S still false-abstained on documented
settlement sharing (turn 2), and returned two wrong-App answers (3 and 4).
Its first 20-turn holdout had another settlement false abstention and one
misleading wrong-App positive. Final boundary changes address some of these
mechanisms; the cancelled replay does not establish that every case is fixed.

Final T's 12 untouched turns scored **7 / 1 / 4**. Both supported discovery
requests selected the correct App with source-backed evidence. No unsupported
positive claim or wrong-App answer was observed in these twelve turns. However:

- A provider question after an unsupported weather request reused the weather
  capability check, despite correct Rasa `detail` and a retained App/provider.
- A reference to the product discussed before a failed new search returned
  `none` in identity-only interpretation and unnecessarily asked for an App.
- A natural request to contrast displayed roles became clarification even though
  Rasa correctly predicted `compare` with confidence 1.
- A supplier question became an access answer. Explicit native-name precedence
  correctly overrode the model's wrong ordinal App, but could not repair its
  wrong operation. Rasa also incorrectly labelled this utterance `out_of_scope`
  with confidence approximately 0.9997.
- One unsupported capability question safely withheld a recommendation but lost
  its singular scope. A purpose question answered correctly despite taking an
  unnecessary capability route; component errors are scored separately from
  answer usefulness.

Rasa's coarse boundaries still mix predicate selection and comparisons and do
not identify the requested metadata field. Confidence is not enough to choose
policy. Qwen can retain an old need instead of interpreting the current question;
source checks then safely assess the wrong goal. These observations do not
establish a retrieval miss: both final supported discoveries ranked the right
App first, and metadata was present in the authorized source. Broad-catalogue
retrieval/ranking remains a separate phase.

On R, prepared responses had median 0.393 s (66 turns, range 0.249–6.093 s).
Final T's assisted replies had median 83.177 s (12 turns, range 18.215–88.242 s);
the identity-only call was 18.215 s. These are cold serialized measurements,
not improvements over a comparable warm baseline. Full final interpretations
logged 701–827 input tokens, below the configured 2048-token context, with no
output-budget error. The owned 4B worker used about 2.6 GiB and was capped at
1.5 CPU cores; no stronger model or shared inference request was used.

Final code passed 1,342 unit tests, the 80% shared-package branch-coverage gate
(86.18%), Ruff and diff whitespace checks. The approved Angular source and all
existing deployment configurations are unchanged. **NLU/context remains open**:
ordinary metadata/reference/comparison requests and settlement paraphrases still
need demonstrated reliability; these local changes are an engineering checkpoint,
not acceptance of the whole phase.
