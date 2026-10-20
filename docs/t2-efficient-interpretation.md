# One-pass English Store understanding

This local follow-up starts at `92d050a`. It is prototype engineering, not a
Mid-Term Report, deployment, or claim of proposal acceptance. The existing private
8096 deployment, demo, Store synchronization, E5 and databases remain unchanged.

## Change and boundaries

The previous ordinary recovery path could interpret, draft, review, repair and
review again. A weak reviewer rejected useful drafts, while unsupported prose
could still appear in failed attempts. The cached 2B CPU runs took roughly
285–358 seconds without serving useful answers.

The ordinary English path now tries the existing prepared route, then makes at
most one structured Ollama call. The model returns a short functional query, source task reference and
dialogue mode, with no prose, quotations, prices or eligibility receipt. Tasks
come automatically from current, checksum-bound source preparation. The same sole
suitability assessor must support each task before it enters the prompt and must
assess the interpreted request before recommendation. Unrelated topics may select
`none`. No App-specific explanations, question answers, synonym catalogue, model
dependency, migration, alternative recommender or persistent service is added.

The source task is a semantic intent label. Known vocabulary derived by the
existing English preparation can recover a uniquely matching task when the model
omits its key. Compound queries need complete vocabulary coverage, while numeric,
negative and other explicit restrictions retain the original request. Unknown
compound functions are not replaced by an available source task. No new synonym
list is introduced.

The application owns discovery versus inspection, current native identities,
filtering, reference binding and final revision/membership checks. First-turn
functional requests cannot become mere App descriptions because the model chose
an inspection mode. Explicit restrictions retain the original request; an AND
cannot disappear during normalization. Capability questions retain the original
need. Task selection is probabilistic language understanding, not proof of semantic
equivalence: a mistaken match can still cause an irrelevant recommendation or
abstention. Real conversations, including compound negatives, are essential.

Source composition prefers relevant, concise facts, retains antecedents instead
of detached references, avoids overlapping source paragraphs, preserves the topic
in simplification and compares Apps in the established discovery context. Pricing
continues to distinguish a listed zero from confirmed free use. Failed discovery
offers partial-fit exploration/provider questions instead of repeating a bare
no-match. No unreviewed model-written factual answer is served by this path.

Rasa still runs over HTTP and its actual intent/confidence/entities are retained
in the widget evidence. Rasa help classification selects a useful recovery
message after an actual no-match, without changing eligibility. It cannot turn unsupported capabilities
into recommendations. Resolved native references outrank model comparison acts.
The existing NLU model is poorly calibrated for natural
Store requests; its confident comparison/help labels must not erase the user's
goal. The common policy retains validated conversational controls and explicit
references. Rasa calibration remains a separate technical gap, not a solved KPI.

## Reproduction

Use the existing [widget recorder](../evaluation/t2/widget.cjs), a loopback-only
disposable gateway/chat/Expert stack, its own sessions/events database, and the
existing read-only Discovery/catalogue endpoints. This avoids duplicating E5 or
altering the protected Store data. In this evaluation the shared Discovery service
was the unchanged 8096 deployed version; modified gateway/chat/Expert code came
from this worktree. No local in-process adapter or authored App catalogue supplied
the answers. The two authorized Store Apps were EdgeConnect and Semantic Treehouse.

The same frozen twelve-turn conversations cover discovery, context, settlement,
simplification, semantic definitions, unsupported automatic rewriting, recovery,
comparison, price and compound/negative requirements. Additional questions are
frozen separately before their first model run. Retain complete rendered text,
SSE, identities, actual NLU, source projections, settings, failures and resource
samples outside Git. Authored user questions are evaluation inputs; the Apps and
answers must be actual synchronized records and actual widget output.

Inference uses pinned Ollama 0.32.0, constrained JSON, temperature zero, non-thinking
mode, no continuation or retry, an 80-token output ceiling, and a wall-clock
deadline. The pinned [Ollama 0.32.0 API contract](https://github.com/ollama/ollama/blob/v0.32.0/api/types.go)
defines constrained format, context truncation and shifting controls.
`truncate=false` and `shift=false` protect exact context limits. A small
configured context and batch size avoid allocating memory for unused tokens.
Generation-free responses remain generation-free. Configuration is documented in
the [reference](configuration-reference.md#contextual-english-store-reasoning).

## Resource and acceptance observations

The VM has two CPU cores and about 5.7 GiB RAM. Initial available RAM was about
2 GiB. Unloading the evaluation 2B model and closing its browser recovered about
3.4 GiB, allowing a bounded 4B trial without stopping existing services. The
candidate download was 2,497,293,316 bytes including metadata layers; its registry
digest was verified by Ollama. Downloads and derived configuration stayed outside
Git; original model caches were mounted read-only.

`qwen3:4b-instruct-2507-q4_K_M` loaded under a 2800 MiB memory/swap ceiling and
1.5-CPU quota with two inference threads. At 4096 context tokens, real requests
exceeded that container's limit and killed its evaluation runner. That failed
configuration is retained as evidence. Reducing context to 2048, using q8_0 KV
cache with flash attention and a 128-token batch allows a smaller allocation.
There is no extra swap allowance for this model container. These limits isolate
the experiment; they do not establish capacity for concurrent users or long
catalogues. A larger context needs additional RAM.

The matched four discovery turns (three distinct requests plus one warm repeat)
returned the intended App in 4/4 cases with 4B versus 1/4 with the same cached 2B
text weights. Across the broader 4B replay, discovery succeeded on 7/9 turns
(including one prepared request and one repeat); excluding those, 5/7 distinct
natural requests succeeded. These are manually assessed engineering cases, not a
pilot accuracy estimate. All six unsupported/compound-negative probes withheld
recommendations; no unsupported factual claim was observed on reading the retained
answers against their source projections. This does not establish general safety.

The 4B loaded-model allocation reported 2.49 GiB; sampled container accounting,
including file cache, reached 2.73 GiB. The 2B API-reported loaded allocation was
1.22 GiB; its container also retained file cache from the prior 4B trial, so that
number alone is not a total RAM budget. Two inference threads saturated the
1.5-CPU quota. Its first cold widget turn took 48.779 seconds; subsequent assisted
turns took 10.255–16.251 seconds (median 12.284). Prepared turns took 0.329–0.601
seconds. The 2B cold turn took 22.010 seconds, with warm assisted turns
7.499–9.291 seconds (median 7.890). 2B is faster but substantially less useful on
these matched requests. Neither model is a blanket English-quality acceptance.

The 4B model is the better **experimental** choice from this narrow comparison.
The measured configuration used `OLLAMA_MODEL=qwen3:4b-instruct-2507-q4_K_M`,
`OLLAMA_THINK=false`, `STORE_MODEL_CONTEXT_TOKENS=2048`,
`STORE_MODEL_TIMEOUT_SECONDS=90`, `STORE_MODEL_THREADS=2`,
`STORE_MODEL_BATCH_SIZE=128` and `STORE_MODEL_KEEP_ALIVE=10m`, with one loaded
model/parallel request on the bounded Ollama server. The cached comparison used
`hedge-qwen-text:2b-q4_K_M`: the same existing 1.9B Q4_K_M text weights, with its
unused vision projector omitted, not a different trained model.
The 4B candidate is not made the repository default; nothing is enabled on port 8096.
Exact model manifests, raw widget/SSE transcripts, source projections and resource
samples are retained locally under
`/home/ubuntu/.local/share/hedge-t2-single/evidence/`; `conversations.md` contains
complete rendered before/after and model-comparison sessions, including failures.
The baseline is the unchanged deployed `f891831` on 8096; historical multi-stage
`92d050a` failures are separate evidence, not a controlled timing comparison.

Remaining failures include the natural request to pool flexibility and approach
the market together, a topic switch to agreeing on payload field meanings, and a
follow-up about tracking contributions for payment. Settlement explanations remain
jargony, and source-only shortening is not consistently a useful simplification.
A short fragment such as “Even simpler, please” also failed. Recognized repeated
simplification controls now remain on the prepared route; state mutation is no
longer mistaken for proof of a completed prepared answer. The final three-turn
prepared simplification replay took 0.663, 0.542 and 0.493 seconds, with no model
calls; the first simplification used the fuller prepared form and the repeat
used its shorter form. A stale-state/model-act
reference bug was corrected and rechecked through a complete comparison → other
App → price conversation.

The resource guard caused a runner OOM only in the rejected 4096-context trial;
there were no new model OOM events in the final 2048-context runs. Host swap use
increased during evaluation, so spare RAM and single-user latency are still
material constraints. Do not use this VM result as concurrent-user capacity.

Verification: 1,289 unit tests, shared branch coverage above the 80% gate, Ruff,
OpenAPI export (no schema changes) and actual browser service-boundary replay.
Model contract tests validate boundaries, not recommendation quality. Full
conversation outcomes and measurements belong with the private transcript bundle.
Two Apps and a small engineering replay cannot establish pilot relevance,
large-catalogue scalability, general model safety, or T2 quality completion.
Remaining weak answers must be reported alongside successful ones. Turkish work,
deployment, Jira, report drafting and changes to existing Store data are outside
this local task.
