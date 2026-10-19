# Prepared Store discovery

The [automatic English preparation and M2M follow-up](store-m2m-preparation.md)
removes manual explanation import as a dependency for new or updated Apps.
It documents the current credential rejection and extractive-quality limits.

Implementation and local evaluation, 2026-10-19. This work is local only: no push,
branch merge, deployment, source catalogue mutation or Jira transition.

The [local conversational UX follow-up](evidence/2026-10-19-conversational-ux.md)
records actual EN/TR widget conversations, fixes and 20/100/300-App synthetic
runtime measurements. SCRUM-39 has since been integrated at `0a02b5a`; its
application changes are already in this branch and were not copied or merged again.

## Source baseline and review boundaries

The isolated `perf/prepared-store-discovery` worktree starts at `c881c6d`, including
SCRUM-39's existing suitability implementation and integrated SCRUM-28/38 at
`eddb179`. It also deliberately reuses the related Store workspace, synchronization,
metadata UI and conversation work through `c6050ab`. Local prerequisite commit
`de2fc1b` applies that existing work and resolves its overlaps while retaining
SCRUM-39's candidate separation, identity-only search and model abstention. Its
1,180 unit tests passed before performance changes. It is not new performance
code and should be reviewed as a dependency composition, separately from the next
commit. No existing source branch was changed or merged. The integration branch,
pending suitability branch, other worktrees, private runtime and preserved demo
remain separate. Do not apply the entire dependency diff blindly to an integration
branch that already contains some of this work.

## Bottleneck and architecture

The former Store path can interpret a turn, draft prose, review it, repair and
repeat. Its planner timeout is 180 seconds; drafting/review each permit 240
seconds. A second search directive can repeat synthesis. General recommendations
also invoked a 40-second structured model selector. Generated text is buffered for
validation, so streaming does not make those computations faster.

The existing services, PostgreSQL projection, reconciliation locks, revisions,
outbox, Qdrant, E5, Valkey sessions, Rasa and Store transport are retained. No new
service, model, dependency or public Store indexing surface is introduced.

1. **Prepare once per changed App.** Additive migration `0005_store_knowledge`
   stores a rebuildable document beside the authoritative payload. It includes
   the preparation version, source checksum, original source projection, explicit
   field ordering and embedding input. Extraction strips unsafe markup while
   retaining full bounded source text, extraction uncertainty, native identity,
   connector/type/billing fields and source version order. This base document is source-derived knowledge. Optional reviewed explanations
   can be prepared separately as described below; generated text is never indexed.
2. **Incremental synchronization/indexing.** Unchanged source checksums and
   preparation versions reuse that document. Missing/outdated preparation repairs
   during reconciliation without inventing a new source revision. The existing
   index repair skips unchanged App vectors; source, embedding model/revision or
   preparation-version changes trigger replacement. Metadata is still committed
   before its derived index, and lexical retrieval remains usable during lag.
3. **Cheap requests.** Routine Store turns use the existing `StoreDialogue` through
   `StoreConversation`: browse, identity/details, reference binding, source-field
   inspection, publisher filtering and comparison require no LLM. Discovery still
   uses lexical/E5 retrieval and the existing SCRUM-39 `assess` function, with bounded grammar additions for
   purpose/provenance forms reproduced in the actual README evidence. Unknown
   predicates and capability qualifications still remain uncertain. Public
   v1/v2 recommendation routes also default to that evidence decision, without
   model selection. Ranking never establishes suitability; unsupported candidates
   remain distinct from recommendations.
4. **Source-grounded explanations.** The original quotation fallback attributes
   exact Store field values. Offline reviewed bilingual prose can explain the same
   evidence without repeatedly displaying quotations. README provenance
   headings/URLs do not become capabilities; deployment restrictions remain
   scoped restrictions. Ambiguous historical purpose statements remain uncertain
   without an explicit descriptive context.
   The existing 1,200-character whole-quotation rule remains: oversized quotations
   are explicitly omitted, while complete bounded evidence remains in the App
   projection. Comparisons describe source differences without inferring a winner.
5. **Language and conversation.** English and Turkish controls support browsing,
   ordinal details and comparisons. A small reviewed Turkish query vocabulary
   maps common domain/request terms into the existing evidence matcher; unknown
   words, negation, conjunctive requirements and quoted names survive. Source
   metadata stays in its supplied language. This is bounded language support,
   not general Turkish translation. Sessions bind identities; follow-ups read
   current rows. Ambiguous names/references and wrong-case native IDs clarify.
6. **Safe caching and change checks.** Only source preparation is newly cached.
   Its checksum/version/identity must match the authoritative row; old documents
   fall back to fresh extraction. Store rankings and conversational responses are
   not newly cached. Every visible App/candidate is resolved again before reply;
   a concurrent update/withdrawal clears the result and references. JSONB ordering
   cannot reorder source quotations because field paths are retained separately.
7. **Optional bounded reasoning.** Explicit `Reason in depth:`, `Analyze in depth:`
   or `Ayrıntılı değerlendir:` requests may invoke the existing grounded expert
   when enabled. The default is off. One eight-second budget (configurable up to
   fifteen) covers drafting and review; it has no repair/retry loop and a 256-token
   output bound. Invalid, incomplete, unavailable or late generation retains the
   useful prepared reply. Reviewed model abstention can veto a recommendation;
   it cannot promote unverified candidates, change native IDs/order or invent a
   new match. Optional prose still uses the existing semantic review, not a
   mathematical factual guarantee.

Routine readiness no longer depends on Ollama. The private workspace warms the
query encoder before serving even when all stored vectors can be reused; a
restart must not move model loading back into the first discovery turn. The workspace launcher starts no
Ollama daemon or model when reasoning is disabled. A dedicated refresh lock lets
background source/index preparation proceed without holding the conversation
turn lock; dialogue serializes turns per session with weakly held locks. An optional
reasoning turn cannot hold the turn lock for unrelated chats. This remains a
single-process adapter, not a new distributed session-locking service. Late source
rechecks cover both routine and generated replies.

## Configuration and activation

All changes remain inactive in the currently running workspace. Reviewed activation
would use its existing launcher and migrations, not a second deployment:

| Setting | Default | Meaning |
|---|---|---|
| `STORE_REASONING_ENABLED` | `false` | Permit explicit complex-turn generation |
| `STORE_REASONING_SECONDS` | `8` | Shared drafting/review budget, >0 and ≤15 seconds |
| `STORE_SYNC_INTERVAL_SECONDS` | `86400` | Existing private Store polling loop; 60–86400 seconds |

The daily default follows the Store team's recommendation. It does **not** satisfy
or supersede the proposal's stricter two-hour publication-to-search commitment;
that conflict still requires owner agreement. The generic ingestion scheduler is
unchanged. Public Store ingestion/indexing and visibility/authentication gates are
not enabled by this work. A failed authorization/transport observation retains
previous source data with its existing status; it is not a successful empty Store.

## Reproducing measurements

Use only an owned mode-0600 saved Store JSON outside Git, or authored fixtures.
The benchmark never needs a Store token or makes Store calls. It starts a loopback
HTTP server inside the existing disposable runner; each measured response includes
HTTP, current metadata reads, recommendation/dialogue policy, Valkey session work,
PostgreSQL impressions and serialization. Inter-service requests use the existing
local Python bridges. Native Store UI rendering, external TLS, multi-process
service hops and production load are outside this timing boundary.

```sh
bash scripts/store-v1-playground.sh --benchmark --embeddings \
  --apps-json /private/already-fetched-apps.json --store-id STORE_ID --rounds 10
```

`--rounds 10` runs 120 requests over twelve cases: English browsing/details/
comparison, English/Turkish functional discovery, strict unsupported requirements,
no-match, raw pricing, Turkish browsing/details/comparison and publisher filtering.
The probe records field/identity fingerprints, counts, intents, decisions, NLU source and
provenance without source/model text, tokens or native identifiers. It reports
median, mean, nearest-rank p95 and maximum; bootstrap/preparation time is separate.
Use `--ollama --legacy` to exercise the old model path explicitly, with sufficient
memory for the configured model and context. The launcher’s conservative model
memory cap may deliberately reject or fail a large model: failure latency is not
successful model latency. The retained baseline here used a separate two-CPU,
4-GiB capped runner with existing cached runtime/model files; no model choice changed.

Measurements, quality review, verification counts and limits are retained in
[the evaluation evidence](evidence/2026-10-19-store-performance.md).


The probe's `--managed-snapshot` mode exercises the existing durable workspace
adapter, including membership gates and observation-state reads. It requires
`HEDGE_PERFORMANCE_DISPOSABLE=true`, a fresh empty disposable database named
`hedge_store_workspace`, narrow read-only mounts for saved bootstrap/provenance
files, and **no credentials**. Reuse of a populated workspace is rejected before
migration or preparation. The retained managed run used a separate task-owned
Rasa container and the same cached model images; the existing private workspace
and demo were never endpoints of these probes.

## Offline conversational explanations

Ordinary chat reads reusable, source-reviewed bilingual preparation stored in the
existing `prepared_knowledge` document. It adds a short purpose, a genuinely
simpler explanation, a practical task label and up to five facts per App. Each
fact retains an exact complete quotation and field path. Original source metadata
and the vector/lexical index remain authoritative and unchanged.

```sh
python -m scripts.prepare_store_explanations --store-id <native-store-id> \
  --reviewed-file /private/reviewed-explanations.json
```

Run inside the intended isolated local workspace environment after reconciliation;
never point it at the preserved demo. The owned mode-0600 file must live outside
the repository. It contains a list of `{id, checksum, explanation, review}` records.
`explanation` has `version: 1`, `en`/`tr` objects with `summary`, `simple`, `use_when`,
and a `facts` array containing `path`, exact original `quote`, `en`, `tr`.
`review` records `method` (`human_source_review` or `agent_source_review`),
`reviewer` and a concrete `note`. This explicitly records editorial provenance;
it does not assert independent maintainer acceptance or local-model approval.

The importer validates current Store membership, checksum, review provenance,
bounded prose and exact quotation bindings, then uses a checksum/version
compare-and-set. A concurrent source change/withdrawal prevents publication.
Identical preparation is reused. Source updates invalidate it; missing, outdated
or unbound preparation falls back to original evidence. Importing prose does not
fetch upstream, invoke a model, modify source payloads or rebuild vectors. Review
cost is separate from import time and ordinary request latency.

The existing suitability assessor can interpret a reviewed compound passage when
its normal grammar cannot: every request term must occur in both the original
passage and its reviewed English explanation. Generated/edited text is not a new
retrieval source. Concrete parsed restrictions, uninterpreted negative claims,
qualified passages and strict/negative requests cannot be cleared by preparation.
Cards, ranking, Store scope and final source-change checks retain their existing
paths. This extends source interpretation in the existing assessor.

Comparisons contrast user tasks instead of repeating source descriptions.
Simplification replaces jargon instead of appending a glossary. Access and provider
questions answer directly. Contextual detail can add relevant workflow facts.
Failed searches preserve prior reference identities in the current catalogue
conversation mode; subsequent turns resolve current rows. Turkish prose uses
reviewed translations. Explicit source inspection remains verbatim.

The two-App widget evaluation uses **Codex-authored, agent-source-reviewed**
preparation, retained privately outside Git with source bindings and review notes.
No App-specific prose or test questions are in application code. Local-model
preparation experiments failed quotation/semantic checks, including an overcautious
pilot-count interpretation; rejected output was not used. The unsuccessful automatic
writer is not part of the committed implementation. Reliable unattended preparation
across a large real catalogue remains open. Actual complete widget conversations
are the acceptance evidence; synthetic timing tests cannot establish recommendation
or translation quality. The configured runtime models and services are preserved.
