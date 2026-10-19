# Prepared Store discovery

Implementation and local evaluation, 2026-10-19. This work is local only: no push,
branch merge, deployment, source catalogue mutation or Jira transition.

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
   connector/type/billing fields and source version order. This is source-derived
   knowledge, not generated capability claims or fabricated translations.
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
4. **Source-grounded explanations.** Deterministic explanations attribute exact
   Store field values. No generated summary can silently remove a qualification. README provenance
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
