# Astra independent engineering audit — 2026-10-13

## Reference scope and current-checkpoint verification

This dated reference preserves the supplied independent Astra audit verbatim below.
It assessed `adab6f5` plus then-uncommitted Store dialogue and Ollama work;
the Ollama work was subsequently completed in `f9fddf0`. It is evidence for that
audited snapshot, not a blanket defect list verified against the latest HEAD.
The original author's “Confirmed” labels and recommendations remain reported
findings. Reproduce each finding against current code before implementing a fix;
links, external observations, and historical results retain their original scope.

The documentation checkpoint on 2026-10-13 verified a clean tracked tree at
`f9fddf05470ada0575ada63ad647d94a98fbc6a0`, matching the live Forgejo integration
branch. Intentional unrelated untracked material was preserved.

A limited offline check of `evaluation/evaluate.py` at that HEAD reproduced
three counterexamples from finding 7, using unmodified function bodies with
mocked search/HTTP dependencies and no network or runtime access:

- `_check_explanation_quality()` accepted invented savings/certification claims
  as `quality_pass=True`; this structural check does not establish factual accuracy.
- `evaluate()` reported `total_queries=10`, `evaluated=1`, and `hit_rate_at_2=1.0`
  for one correct result and nine mocked timeouts.
- `stream_evaluate()` counted a stream containing only a `problem` event with
  status 503 as evaluated and printed `[OK]`.

These are verified evaluator behaviors at the checkpoint revision, not a live
acceptance experiment. No other audit finding was reproduced during this
checkpoint; no full application suite, authenticated Store operation, live model,
or demo/runtime check was run. No application defect was fixed.

## Original supplied audit (verbatim)

**HEDGE-ExpertAI is an integration-stage engineering prototype with useful infrastructure, but its central product promise remains unproven.** Several safeguards are well designed. However, important implemented behaviors contradict the requirements, and parts of the evaluation machinery can report success for incorrect or failed results.

The highest-value next step is to establish one trustworthy Store-to-user flow and measure it correctly. Further expansion of synthetic catalogues, dialogue rules, or model experiments would currently risk reinforcing mistaken assumptions.

I audited commit `adab6f5` plus the current uncommitted work, including the Store dialogue and Ollama additions. I changed no files or runtime resources, accessed no credentials, and made no authenticated requests.

### 1. Executive assessment

The original purpose is clear: understand a user’s need, infer App utility from registered metadata, and help the user discover suitable applications inside HEDGE. The official Topic 15 description independently confirms this emphasis on utility, functionality, and input/output metadata. Ontology mapping is a separate Topic 16; comprehensive SAREF coverage is not a prerequisite for ExpertAI. [Official applicant guide, pp. 13–14](https://hedgeiot.eu/wp-content/uploads/2025/07/HEDGE-IoT-OC1-Guide-for-Applicants.pdf)

The proposal adds specific acceptance commitments:

| Commitment | Assessment |
|---|---|
| Relevant App in the first two suggestions for ≥70% of pilot queries; ≥50 jointly defined queries | No trustworthy real-Store acceptance evidence. Existing evaluation has material defects. |
| Average response below five seconds | Unproven with the complete real-model stack; concurrency and measurement problems undermine current evidence. |
| Publication-to-search within two hours | Store scheduling/indexing remains disabled. Daily polling conflicts with this objective. |
| Expert LLM layer; ≥80% contextually accurate explanations | Ordinary v2 validation does not check factual support. Draft Store generation performs bounded quotation selection. |
| ≥70% of pilot sessions include a clicked/followed recommendation | Current analytics measures a different population and action. |
| Integrated plug-in and ≥10 recorded complete interactions | Native Angular integration and retained qualitative acceptance remain outstanding. |

These commitments were checked against both the [tracked proposal](/home/ubuntu/hedge/docs/proposals/HEDGE-IoT-OC1-Proposal-HedgeExpertAI.md:44) and the supplied original DOCX. Their substantive requirements agree.

There is substantial work worth preserving:

- Native Store/App identity is retained without fabricating the synthetic v2 schema.
- PostgreSQL owns local catalogue state; vector and cache candidates are checked against current records.
- Source-scoped reconciliation, transactional revisions/outbox, and conservative absence handling address real integrity problems.
- The Store client uses HTTPS, bounded responses, sanitized failures, and conservative completeness assumptions.
- Dependency pins, deployment hardening, and focused regression tests provide a useful engineering foundation.

These are implemented mechanisms, not proof of complete product acceptance. The two-App authenticated smoke test remains recorded evidence from an earlier authorized exercise; I did not repeat it. The preserved demo’s deterministic generation also establishes no live-model quality.

**The project’s strongest progress is in infrastructure correctness and containment. Its weakest areas are faithful interpretation of user needs, use of available metadata, recommendation validity, and measurement.**

### 2. Evidence and external-contract assessment

I treated the evidence sources separately:

| Source | What it establishes |
|---|---|
| Original proposal and official call | Intended outcomes and proposed commitments; signed amendments were not available. |
| Supplied stakeholder reply | Deployment-specific integration guidance and offers of support. |
| Public Store documentation/OpenAPI | Documented interfaces and lifecycle behavior, with inconsistencies and omissions. |
| Public deployed Angular bundles | Observable current frontend implementation, not a guaranteed future contract. |
| Repository code and counterexamples | Implemented behavior in this working tree. |
| Historical reports and test results | Evidence for their particular revision and environment only. |

On 13 October 2026, direct unauthenticated HTTPS reads established:

- Documentation and raw OpenAPI returned **200**.
- `getAllApps` for the supplied Store and `getAssets` returned **401**.
- The OpenAPI SHA-256 remains `f5090c9cad06ea314a70ca1676dc433d97006ddbd7a65f9273058480239793a3`, matching the repository’s recorded snapshot.
- The specification documents considerably more App metadata than ExpertAI currently retains.

The browser research tool could not load the Store origin, but direct HTTPS retrieval succeeded. No authentication bypass was attempted. [Store documentation](https://store.haslab-dataspace.pt/docs/index.html), [raw OpenAPI](https://store.haslab-dataspace.pt/backend/api/v1/api-docs)

Several external assumptions need correction:

| Assumption | Evidence-based correction |
|---|---|
| Store metadata cannot support compatibility or price questions | OpenAPI includes `builtForConnector`, `connectorVersion`, `type`, `billable`, `price`, and `dataspaceAppDescription`. Their actual population and business meaning remain unverified. |
| `visible && active` is the confirmed publication rule | The deployed App Explorer filters on `visible`; `active` is passed to a badge. ExpertAI’s additional gate is conservative policy, not established Store semantics. |
| Visible Apps are anonymously public | Documentation and the stakeholder reply describe availability to Store users. Backend reads require authentication. Redistribution through anonymous ExpertAI endpoints needs an explicit decision. |
| Richer descriptions necessarily require an external App–Asset join | An embedded Dataspace description already exists on `App`; the frontend parses it. Its safe use deserves investigation before assuming a separate join is mandatory. |
| Certification is required for HEDGE publication | Generic documentation describes certification; the stakeholder reply explicitly says HEDGE does not apply that routine. |
| A two-hour timer would prove two-hour freshness | Fetch, processing, retries, and indexing add delay. Daily polling cannot meet the stricter objective without an agreed change. |

The public Angular implementation currently uses `/apps/app-details/:id`, so navigation behavior can be investigated independently. That observed route still needs to become an agreed integration contract. [Deployed App module](https://store.haslab-dataspace.pt/5.f86649fb085d6f8c258c.js), [lifecycle documentation](https://store.haslab-dataspace.pt/docs/app-lifecycle.html), [stakeholder reply](</home/ubuntu/hedge/docs/HEDGE_ExpertAI_—_Essential_Integration_Questions_repliedFCoelho.docx>)

### 3. Prioritized findings

“High” means material to product correctness or a blocker before the relevant pilot/public operation. Conditional exposure risks are identified explicitly; I found no evidence of a current production compromise.

**1. High — The source projection discards information central to the product. Confirmed data loss; live field coverage unknown.**

`normalize_store_v1_app()` drops connector compatibility, App type, billing/price, and embedded Dataspace descriptions. Search uses only name, description, and provider. README is retained but excluded; recommendation output loses even other retained fields such as version information. [Normalizer](/home/ubuntu/hedge/services/metadata-ingest/app/client.py:24), [search and recommendation projection](/home/ubuntu/hedge/shared/hedge_shared/store_v1.py:132)

I executed the actual normalizer with a constructed App containing compatibility, billing, README capabilities, and embedded feature metadata. The resulting search text was only:

```text
Connector . Data integration.
```

All six tested structured fields were discarded.

Consequently, “the source cannot answer that” can mean “our projection threw the answer away.” This materially limits utility inference and comparisons.

The correction is a provenance-preserving projection of useful, confirmed fields. It should distinguish unavailable facts from unsupported interpretations. Price does not establish currency or licensing; connector fields do not prove compatibility with every deployment. Embedded JSON and README remain untrusted data, but that does not justify permanently excluding all their useful content.

**2. High — Ordinary v2 “grounding validation” admits fabricated facts. Confirmed.**

The narrative checks require App titles to appear in order and inspect nearby English ranking words. They do not verify factual claims against metadata. [Validation functions](/home/ubuntu/hedge/services/expert-recommend/app/recommender.py:76), [admission decision](/home/ubuntu/hedge/services/expert-recommend/app/recommender.py:220)

Using the actual functions, both checks accepted this explanation when the source descriptions merely described displaying readings:

> Energy Meter guarantees 90% electricity savings and is medically certified. Water Monitor is free forever and legally approved in every country.

This proves a validator defect, not the incidence of such output from the live model.

The architecture and traceability currently overstate what this mechanism establishes. Title/order validation is useful, but it cannot establish grounded explanations. The draft Store work correctly acknowledges this limitation. [Architecture claim](/home/ubuntu/hedge/docs/architecture.md:42), [draft acknowledgement](/home/ubuntu/hedge/docs/store-v1-ollama-evaluation.md:20)

**3. High — Retrieval candidates become recommendations without establishing suitability, and valid abstention can be overridden. Confirmed.**

Dense retrieval discards similarity scores. Public relevance bands depend on rank and whether both retrieval branches returned the App; every top-five v2 result receives at least “medium.” This provides no demonstrated relevance threshold. [Candidate handling](/home/ubuntu/hedge/services/discovery-ranking/app/searcher_v2.py:96), [relevance bands](/home/ubuntu/hedge/services/discovery-ranking/app/searcher_v2.py:183)

A counterexample using the actual narrative function:

- Query: “Find earthquake warning apps.”
- Candidate: “Water Meter.”
- Model response: “None of these apps meets the requested requirement.”
- Served fallback: “Start with **Water Meter** because it is the highest-ranked evidence-backed match.”

The title validator rejects that abstention and the fallback asserts a match. [Fallback](/home/ubuntu/hedge/services/expert-recommend/app/recommender.py:55)

Ranking and supported suitability need separate decisions. Preserve legitimate abstention, and calibrate behavior on positive, ambiguous, and no-match queries. An arbitrary cosine cutoff would not resolve this by itself.

**4. High — Optional SAREF becomes a mandatory filter for ordinary domain requests. Confirmed requirement contradiction.**

The classifier maps words such as “energy” to a SAREF extension. Normal chat and streaming then insert that inference as a hard filter. Both lexical and dense-result resolution require matching annotations. [Entity inference](/home/ubuntu/hedge/services/chat-intent/app/classifier.py:140), [chat filter insertion](/home/ubuntu/hedge/services/chat-intent/app/routes.py:484), [filter enforcement](/home/ubuntu/hedge/services/discovery-ranking/app/searcher_v2.py:85)

An App with a matching energy-monitoring description but no ontology annotation fails the actual filter for “Find apps for energy monitoring.”

This contradicts the proposal’s explicit optional-signal requirement. It also risks narrowing multi-domain requests to the first recognized domain. The isolated Store policy bypasses this behavior, so its tests do not establish correctness of the normal route.

Inferred domain concepts should influence ranking unless the user explicitly requests a restriction.

**5. High — The lexical fallback does not support ordinary conversational searches reliably. Confirmed construction defect.**

The entire query enters `websearch_to_tsquery('simple', ...)`. Unquoted terms are joined with AND, and the built-in simple dictionary does not remove conversational stopwords. [SQL construction](/home/ubuntu/hedge/shared/hedge_shared/storage.py:607), [PostgreSQL semantics](https://www.postgresql.org/docs/16/textsearch-controls.html#TEXTSEARCH-PARSING-QUERIES), [dictionary configuration](https://raw.githubusercontent.com/postgres/postgres/REL_16_STABLE/src/include/catalog/pg_ts_dict.dat)

Therefore “Find apps for energy monitoring” requires the word `find`. None of the 120 synthetic records contains that word. Under the shipped configuration, this ordinary request has no lexical candidates. This conclusion follows from source inspection and PostgreSQL semantics; I did not query a running database.

Existing outage tests search the single keyword `energy`, concealing this failure. [Test helper](/home/ubuntu/hedge/tests/integration/test_index_consistency.py:185), [outage test](/home/ubuntu/hedge/tests/integration/test_index_consistency.py:340)

Two additional recall problems compound it:

- Only English title/summary/keywords enter the lexical document, despite seven additional supplied translations. [Index construction](/home/ubuntu/hedge/shared/hedge_shared/storage.py:206)
- Dense candidates are truncated before filters. An actual-function probe returned 41 candidates, with only number 41 matching the requested publisher; the function retained 40 and discarded the sole match. [Truncation](/home/ubuntu/hedge/services/discovery-ranking/app/searcher_v2.py:105), [later filtering](/home/ubuntu/hedge/services/discovery-ranking/app/searcher_v2.py:254)

These require query construction and candidate-selection fixes before weight tuning.

**6. High — Dialogue often changes the user’s request instead of preserving its meaning. Confirmed.**

Normal v2 detail requests rerun general search with an App ID embedded in prose. Comparisons search concatenated previous titles. Natural-language refinements are appended to a query rather than translated into enforced constraints. [Dialogue construction](/home/ubuntu/hedge/services/chat-intent/app/routes.py:391), [detail handling](/home/ubuntu/hedge/services/chat-intent/app/routes.py:488)

The isolated Store policy improves identity resolution but introduces other mistakes. Actual-function probes produced:

| Input | Implemented behavior |
|---|---|
| “Find alternatives to EdgeConnect” | Searches only `"EdgeConnect"` |
| “Find apps for 2 buildings” | Treats `2` as a previous-result reference; performs no search |
| “Find apps that support MQTT” | Refuses the request even when the supplied description says it connects MQTT devices |

The causes are broad unsupported-word rules, unrestricted ordinal detection, and replacement of the entire query with matched names. [Store policy](/home/ubuntu/hedge/services/chat-intent/app/store_dialogue.py:58)

The simplest sound direction is one policy producing explicit actions: search, refine constraints, resolve selected identities, and compare selected identities. Preserve the original request and clarify unresolved references.

**7. High — The executable evaluator can report success for fabricated explanations and predominantly failed runs. Confirmed.**

“Explanation accuracy” is based on message length and absence of two fallback phrases. Expected App IDs are unused. Failed requests disappear from quality and latency denominators. SSE `problem` events are treated as normal termination. [Quality proxy](/home/ubuntu/hedge/evaluation/evaluate.py:255), [denominators](/home/ubuntu/hedge/evaluation/evaluate.py:208), [stream handling](/home/ubuntu/hedge/evaluation/evaluate.py:354)

In-memory executions of the actual functions established:

| Constructed case | Evaluator result |
|---|---|
| Long, wholly fabricated explanation | Quality passes |
| One correct search and nine timeouts | HitRate@2 = 100% |
| Stream containing only `problem: 503` | Counted as evaluated; printed as OK |

Other mismatches include median replacing the objective’s average, returned Apps replacing qualified visits, and v2 analytics being read using old feedback field names. [Reported KPI checks](/home/ubuntu/hedge/evaluation/evaluate.py:444)

This must be corrected before conducting acceptance experiments. Human contextual accuracy cannot be replaced by structural output checks.

**8. High — Recommendation acceptance measures helpfulness votes among respondents, not adoption across pilot sessions. Confirmed.**

The SQL includes only sessions with explicit acceptance/dismissal feedback. Silent sessions disappear; `app_opened` never establishes an accepted session. The widget’s “Was this helpful?” answer becomes `recommendation_accepted`. [KPI SQL](/home/ubuntu/hedge/shared/hedge_shared/storage.py:746), [widget mapping](/home/ubuntu/hedge/frontend/widget/hedge-expert-widget.js:858)

Executing the extracted query against in-memory fixtures produced:

- 100 session impressions, one helpful vote: **100% acceptance**.
- 100 session impressions, 100 App clicks: **acceptance undefined**.

The proposal defines acceptance through clicking/following recommendations. Satisfaction and adoption need separate metrics and denominators.

Retention also removes the App identities needed to reconstruct the ≥60% qualified-App-visit target after 30 days. Aggregated distinct-session counts cannot reconstruct the required session unions. [Retention aggregation](/home/ubuntu/hedge/shared/hedge_shared/storage.py:788)

Define minimal retained outcome aggregates before collecting the pilot; retaining all raw interactions indefinitely is unnecessary.

**9. High — Widget Markdown permits HTML attribute injection. Confirmed renderer defect; exploitability depends on the host page.**

`escapeHtml()` escapes text-node markup, but quotes remain. The Markdown link replacement interpolates the matched URL into a quoted HTML attribute. Assistant output is assigned to `innerHTML`. [Renderer](/home/ubuntu/hedge/frontend/widget/hedge-expert-widget.js:156), [output insertion](/home/ubuntu/hedge/frontend/widget/hedge-expert-widget.js:704)

The actual renderer and an HTML parser confirmed:

```text
[open](https://example.invalid/" onpointerenter="window.audit=1)
```

creates an actual `onpointerenter` attribute.

The gateway’s CSP mitigates inline-handler execution on its own page. An embedded widget inherits its host’s policy. I did not execute an attack against the demo or Store.

Construct validated links through DOM APIs, or use an appropriately sanitized renderer. Gateway CSP should remain defense in depth.

**10. High before index maintenance — Rebuild/promotion can lose already-delivered updates. Confirmed race.**

Rebuild reads the catalogue in separate batches while outbox delivery continues writing to the old alias. Promotion checks point count, without a coherent snapshot or catch-up boundary. [Rebuild](/home/ubuntu/hedge/services/discovery-ranking/app/indexer.py:249), [promotion](/home/ubuntu/hedge/services/discovery-ranking/app/indexer.py:281)

An in-memory interleaving using the actual functions produced:

```text
Promotion succeeded.
PostgreSQL revision: 2
New live vector revision: 1
Revision-2 outbox operation: already completed
```

Authoritative retrieval correctly rejects the stale vector. That prevents stale metadata from being served, but semantic recall remains degraded because no pending operation repairs it.

For this scale, a bounded maintenance operation that serializes updates, delivery, rebuild, and promotion may be sufficient. Continuous rebuilding would require a snapshot and catch-up mechanism. Counts alone do not validate index consistency.

**11. High before Store activation — Optional metadata errors can prevent publication withdrawals. Confirmed boundary contradiction.**

Reconciliation supports applying valid withdrawals while quarantining malformed neighboring records. The real client, however, normalizes every App and aborts the entire response if any record is invalid. [Client admission](/home/ubuntu/hedge/services/metadata-ingest/app/client.py:319), [reconciliation](/home/ubuntu/hedge/services/metadata-ingest/app/snapshot.py:51)

Actual-function reproduction: App A has `visible:false`; App B has a malformed optional URL. The whole fetch fails, so A’s withdrawal never reaches reconciliation. A malformed optional field on A itself also prevents its publication change.

The test for partial-snapshot withdrawal bypasses this client boundary. [Existing test](/home/ubuntu/hedge/tests/integration/test_catalogue_snapshot.py:116)

Separate safe identification/publication handling from descriptive metadata validation. Define stale-source behavior before public enablement. **Current Store public indexing is disabled, so this is an activation blocker, not evidence of an existing public leak.**

**12. High before public deployment — Trusted forwarding configuration makes limiter identity spoofable. Confirmed conditional defect.**

Nginx appends incoming `X-Forwarded-For`; the gateway trusts the leftmost value whenever the direct peer is trusted. An attacker-controlled initial address therefore becomes the limiter identity. [Nginx](/home/ubuntu/hedge/services/nginx/nginx.conf:57), [gateway selection](/home/ubuntu/hedge/services/gateway/app/middleware.py:48)

The actual function selected `198.51.100.1` from:

```text
198.51.100.1, 203.0.113.10
```

even though the latter was the real client address. Changing the first value changes the bucket. With proxy trust disabled, users behind Nginx instead share its bucket.

Replace untrusted forwarding headers at the edge or validate the chain against the actual proxy topology.

**13. Medium — Valid chat input and infrastructure failure become false “no match” answers. Confirmed.**

Chat accepts 2,000 characters; discovery accepts 500. The query passes through, and `_search_apps_v2()` catches validation failures and outages alike, returning an empty list. The caller reports successful absence of matching Apps. [Request limits](/home/ubuntu/hedge/shared/hedge_shared/models_v2.py:301), [exception handling](/home/ubuntu/hedge/services/expert-recommend/app/recommender.py:134)

A valid 501-character chat request can therefore fail internally and become a misleading product conclusion. Refinement concatenation can cross the boundary too.

Align the contracts or deliberately derive a bounded search query. Preserve the distinction between an empty successful search and unavailable retrieval.

**14. Medium — Synchronous dependency calls block the async chat worker. Confirmed structural behavior.**

Async chat handlers call synchronous classification, which performs synchronous HTTP requests to Rasa. Synchronous session/database operations also run on these paths. [Chat call](/home/ubuntu/hedge/services/chat-intent/app/routes.py:443), [Rasa request](/home/ubuntu/hedge/services/chat-intent/app/classifier.py:166)

With actual route/request functions and a mocked 120 ms blocking dependency, three concurrent requests took 361 ms; an unrelated heartbeat scheduled for 10 ms executed only after 361 ms.

This is a demonstration of event-loop starvation, not a target-host performance benchmark. Use async I/O or bounded offloading, explicit dependency timeouts, and then test delayed dependencies under concurrency.

### 4. Architectural judgment

**Keep the main components and boundaries.** PostgreSQL, Qdrant, Valkey, FastAPI, Rasa, and Ollama are reasonable choices. The evidence does not justify a framework replacement, new orchestration platform, or broader microservice redesign.

The architecture should converge around one maintained product flow:

```text
Approved Store metadata
→ source-preserving local projection
→ retrieval with explicit constraints and no-match handling
→ identity-bound dialogue
→ evidence-supported explanation
→ native HEDGE interaction and correctly defined events
```

Several choices deserve adjustment:

- **Treat the synthetic v2 model as a fixture profile.** Its rich translations, ontologies, licences, and datasets must not dictate what real Store records must contain.
- **Converge experimental and ordinary behavior.** The Store runner replaces HTTP calls with local bridges and injects a separate dialogue policy. It usefully validates components, but bypasses important production contracts—including the query-length mismatch. [Runner wiring](/home/ubuntu/hedge/scripts/store_v1_playground.py:166)
- **Give the LLM a measurable role.** The uncommitted extraction path is safer about invented wording, but it selects description/provider sentences in English. It does not yet establish expert reasoning, suitability assessment, or improved intent understanding. Exact quotations can still omit relevant qualifications. [Draft generation](/home/ubuntu/hedge/services/expert-recommend/app/recommender.py:261)
- **Do not add fine-tuning or personalization without demonstrated need.** The proposal contains both “trained corpus” wording and prompt/domain-adaptation wording. Agree the interpretation. The current corpus manifest contains only an unapproved synthetic source. [Corpus manifest](/home/ubuntu/hedge/corpus/manifest.json:5)
- **Use the preferred native Angular surface.** Maintain the widget as an engineering/demo asset; prioritize an agreed API and native navigation over further parallel frontend expansion.
- **Separate public discovery from personalization.** Generic recommendations can still require access control. Enabling OAuth currently does not require authentication on discovery routes. Store visibility and permitted audience must be settled before exposure.

Validation also needs rebalancing. The 200 generated queries contain no no-match cases, reuse exact synthetic capabilities, and place English capability text inside non-English templates. They exercise plumbing rather than independent user understanding. [Generator](/home/ubuntu/hedge/scripts/generate_evaluation_set.py:29)

CI enforces shared-package coverage and deterministic E2E, but does not run the isolated PostgreSQL/Qdrant integration regression files. The proposal’s core-functionality coverage commitment is broader than the current coverage target. [CI checks](/home/ubuntu/hedge/.github/workflows/ci.yml:59)

The draft Ollama note records the configured model being killed by the isolated memory limit. That is useful fallback evidence; it establishes neither successful generation nor impossibility on an appropriately provisioned target host. [Recorded result](/home/ubuntu/hedge/docs/store-v1-ollama-evaluation.md:114)

### 5. Recommended direction

The work should proceed in the following dependency order.

| Step | Action | Concrete success criterion |
|---|---|---|
| **1. Make evidence trustworthy** | Correct evaluation denominators, terminal failures, accuracy labels, adoption events, and retention aggregates. | The counterexamples above fail correctly; every attempted query and pilot session is accounted for under a documented protocol. |
| **2. Establish the useful source contract** | Inventory actual approved fields, publication/access semantics, embedded descriptions, and missing utility metadata. | Each supported user question maps to retained source evidence; unsupported questions identify the actual missing fact. |
| **3. Correct product semantics** | Fix inferred hard filters, conversational lexical queries, filtering before truncation, reference handling, query limits, abstention, and error distinctions. | Representative searches and follow-ups preserve constraints and App identity; irrelevant candidates and dependency failures receive distinct responses. |
| **4. Close activation blockers** | Fix widget injection, forwarding trust, withdrawal handling, and rebuild consistency. | Adversarial rendering, malformed-neighbor withdrawal, forged forwarding headers, and concurrent rebuild/update scenarios pass through the real boundaries. |
| **5. Complete one native vertical slice** | Connect the offered dummy Store through normal service APIs to the agreed Angular pane and authoritative App navigation. | A user can search, refine, inspect the selected App, compare selected Apps, follow a recommendation, and encounter clear terminal errors. |
| **6. Demonstrate AI benefit and operational fitness** | Compare lexical, hybrid, and LLM-assisted variants on identical held-out tasks; test the complete stack on the target host. | Retained rankings and reviews establish the proposal’s retrieval/explanation targets; measured average, median, tail latency, concurrency, freshness, and recovery satisfy the agreed protocol. |
| **7. Complete acceptance and release evidence** | Run the consented pilot and connect results to deliverables and release artifacts. | Reviewed ≥50-query evidence, ≥10 complete interactions, correctly measured acceptance/exposure, documented release materials, and explicit deliverable acceptance. |

Small representative user scenarios should guide steps 2–3 immediately. The full held-out benchmark should be protected from tuning.

For freshness, choose a polling and processing budget that can actually satisfy the agreed bound. Do not interpret the stakeholder’s daily recommendation as automatic permission to weaken the proposal.

### 6. Questions requiring external confirmation

These remain unresolved after the independently obtainable evidence:

1. **What governs final acceptance?** Are there signed amendments covering deadlines, the two-hour versus daily/24-hour freshness conflict, response timing boundaries, and the intended meaning of corpus training and continuous improvement?
2. **What do Store publication and authorization mean precisely?** Confirm `active`, client visibility scope, withdrawal/deletion behavior, snapshot completeness, and whether visible metadata may be served to anonymous users.
3. **Which useful metadata is populated and authoritative?** Confirm connector fields, App type, billing semantics, embedded Dataspace descriptions, input/output information, and permissions for README/documentation use. Any external Asset join needs an explicit identity/access contract.
4. **What is the unattended credential contract?** The offered backend client still needs approved acquisition, renewal, scopes, lifetime, and operational ownership. Store backend authentication and Dataspace authentication remain separate.
5. **What is the accepted native integration and deployment boundary?** Confirm the initial Angular surface, request/result/navigation contract, incoming assistant access policy, hosting resources, and operational owner.
6. **Who supplies and approves representative tasks?** Required languages, relevant-App labels, no-match cases, pilot cohorts, qualitative consent, and business-impact baselines need stakeholder ownership.

The audit used source tracing, original-document inspection, public documentation and deployed frontend inspection, unauthenticated GETs, and in-memory counterexamples. I did not run the full test suite, target-host load tests, live models, or authenticated Store operations. `git diff --check` passed, and the working-tree change inventory remained unchanged. Existing documentation is appropriately cautious in many places; the findings above show where the implementation and executable evidence still need to catch up with that caution.