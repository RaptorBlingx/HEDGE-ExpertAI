# Manual offline Store testing

For the browser Chat Pane, real-model options and observed limitations, use the
[isolated browser evaluation guide](store-v1-browser-evaluation.md). Both interfaces
reuse the same guarded disposable runner and Store dialogue policy.

```sh
cd /home/ubuntu/hedge
bash scripts/store-v1-playground.sh
# Fixed diagnostic conversation, or optional real pinned E5:
bash scripts/store-v1-playground.sh --examples
bash scripts/store-v1-playground.sh --embeddings
```

Requires Docker and cached PostgreSQL/Qdrant/Valkey images matching repository pins.
Bootstrap installs existing hashed dependency locks and CI-pinned developer tools.
No Store data or credentials are fetched. The CLI creates uniquely named disposable
resources on an internal network, with no host ports, Compose, `.env` reads,
persistent volumes or demo connections. Source is mounted read-only. Only its fresh
`hedge_phase1_test` database receives migrations, fixtures and impressions; a populated
catalogue is refused. EOF, Ctrl-C and normal exit clean up this run. Images remain
for reuse; abnormal cleanup instructions are in the browser guide.

Default `chat>` runs real application-owned Store dialogue and retains Valkey
conversation state. `search>` calls the recommendation orchestrator directly without
changing conversation history. Responses print actual Apps, native identity,
ranking, source quotations and, for chat turns, actual NLU source/confidence.
Search traces show effective queries/filters. Identity follow-ups resolve PostgreSQL
directly rather than pretending they are fresh search rankings.

```text
:records
hello
Show me EdgeConnect and Semantic Treehouse
Tell me more about the second app
Compare the first two apps
What does it cost?
Tell me more about the first app
Does it support MQTT?
:mode search
sensor readings
semantic data models
:filters {"capabilities":["MQTT"]}
EdgeConnect
:filters {}
:mode chat
reset
:quit
```

`:filters` accepts existing typed filters, persists until cleared, and adds no price
or capability inference. Dialogue filters/context can also persist on follow-ups;
`reset` clears that context. `:help` describes modes; invalid JSON/unknown fields are
reported without being applied. There is no transcript export.

Store name/native-ID references and ordinal details now bind selected current Apps;
comparisons quote source fields and preserve original result order. Unsupported
prices/capabilities/metadata fail with a limitation response, not invented claims.
The fixtures contain useful **authored, labelled evaluation descriptions**, not
private or verified product metadata. Missing fields stay missing; no Assets are
recommended or enriched. These are wiring diagnostics, not relevance evaluation.

Default: real PostgreSQL lexical search, normalization/reconciliation, authoritative
hydration/RRF, recommendation orchestration, Store policy, regex NLU, Valkey and
impressions. Service HTTP boundaries are local Python bridges. Real E5 is optional;
Rasa is separately opt-in and demonstrated a serious Store-query misclassification.
Ollama does not run: Store explanations remain deterministic quotations. No constant
vectors or successful answers are simulated. Literal full-text retrieval can miss
long questions even after conservative Store request-boilerplate removal.

See the browser guide for observed multi-turn verification and model limitations,
and [offline projection](store-v1-offline-recommendations.md) for retrieval safety.
Live/public integration still requires the approvals in the
[integration baseline](integration-baseline.md).
