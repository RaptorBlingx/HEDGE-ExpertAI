# Manual offline Store testing

From the integration checkout:

```sh
cd /home/ubuntu/hedge
bash scripts/store-v1-playground.sh
```

For the same fixed diagnostic searches and conversation used below:

```sh
bash scripts/store-v1-playground.sh --examples
```

Requires Docker and cached PostgreSQL/Qdrant/Valkey images matching repository pins.
The first runner build installs existing hashed dependency locks and CI-pinned test
tools; bootstrap may require package-registry access. No models or Store data are
fetched. Subsequent builds use Docker's cache. `--help` runs without starting Docker.

The launcher creates an internal network, uniquely named disposable PostgreSQL,
Qdrant and Valkey containers, and a bounded CLI container. There are no published
ports, Compose profiles, persistent volumes, shared demo resources or `.env` reads.
Source is mounted read-only. Only this fresh `hedge_phase1_test` database receives
migrations/fixtures/impressions. A populated catalogue is refused. Normal exit,
EOF and Ctrl-C remove this run's containers/network and temporary data. The local
`hedge-store-cli:local` runner image remains for reuse; no HEDGE service image changes.
A forcibly killed host shell can leave `hedge-store-cli-tmp.*` resources: inspect
`docker ps -a`/`docker network ls` and remove only names from that specific abandoned
run (runner, sessions, vectors, database, then network). Never use a broad prune.

## Interactive use

Default `chat>` exercises the existing intent/dialogue route and retains conversation
state. `search>` calls the existing recommendation orchestrator directly without
changing chat history. Each answer prints the actual result, intent (chat mode),
ranked Apps with native identity/publication facts, effective retrieval query/filters,
and source-field explanations. No matches are returned as an empty App list.

Try these lines:

```text
:records
hello
EdgeConnect
Tell me more about the first app
:mode search
"Semantic Treehouse"
EdgeConnect OR "Semantic Treehouse"
:filters {"capabilities":["MQTT"]}
EdgeConnect
:filters {}
:mode chat
EdgeConnect OR "Semantic Treehouse"
Compare the first two apps
Which app supports MQTT at the edge?
How much does EdgeConnect cost?
Only free apps instead
Find apps for energy monitoring
reset
:quit
```

`:filters` accepts the existing typed search filters; it does not add capability or
price interpretation. Its values persist across questions/modes until cleared.
Application dialogue context also merges filters on detail/refinement/comparison;
use `reset` to clear that context. `:help` displays commands and limits. Invalid JSON
or unknown filters are reported rather than applied. There is no transcript export.

## What actually runs

- Normal code: Store normalization/reconciliation, PostgreSQL lexical retrieval,
  authoritative hydration/RRF, recommendation orchestration, source quotations,
  `chat_v2`, regex intent fallback, Valkey sessions/events and PostgreSQL impressions.
- HTTP boundaries are replaced by in-process bridges to the same functions. No
  gateway, authentication middleware or FastAPI server is started. Store results
  remain within the existing explicit offline Store/collection scope.
- Rasa is disabled locally, so this is its existing regex fallback, not real Rasa
  NLU. No model is downloaded or demo cache mounted. Dense encoding is explicitly
  unavailable; the real lexical fallback runs. Qdrant is a real isolated server
  with an empty disposable collection, but vector indexing/relevance is not tested
  by this manual runner. Existing regression tests exercise indexing separately.
- Store explanations use the existing deterministic, escaped quotations. Ollama
  is blocked if accidentally called. There are no constant test vectors, generated
  answers, invented relevance scores or model-quality claims.

The [manual fixtures](../tests/fixtures/store-v1/manual-apps.json) retain the two
user-specified names with invented native IDs/publication/date examples. Descriptions,
providers, links and capabilities remain missing; versions cover empty/null shapes.
No private authenticated payload, owner information, Asset-derived feature claims,
prices or assumed product capabilities are copied. These deliberately sparse records
are for wiring diagnostics, not representative retrieval-quality evaluation.

## Observed diagnostic behavior (2026-10-09)

| Input/mode | Actual outcome |
|---|---|
| `EdgeConnect` / search | One App, lexical evidence, name-only source quotation. |
| `"Semantic Treehouse"` / search | One App, lexical evidence, name-only source quotation. |
| `EdgeConnect OR "Semantic Treehouse"` / search or chat | Two Apps, EdgeConnect rank 1 and Semantic Treehouse rank 2 for these fixtures. No quality score. |
| `hello` / chat | Existing static greeting; its comparison wording is not evidence of comparison support. |
| `EdgeConnect` / chat | Regex intent `unknown`, but existing dialogue still retrieves the App. |
| `Tell me more about the first app` after a match | Intent `detail`; ordinal resolves, but the resulting `Explain application <local-id>: ...` lexical query returns no Apps. |
| `Compare the first two apps` after both matches | Intent `compare`; query is `Compare ;  for: ...` because existing dialogue reads synthetic `title`, while Store records have `name`. No Apps. |
| MQTT capability or price question | No Apps; no capability or price answer. A missing match does not establish that the real product lacks the feature. |
| `Only free apps instead` | Intent `refine`; appends the previous query and refinement text, with no price filter or comparative reasoning. No Apps. |
| `Find apps for energy monitoring` | Regex infers a SAREF extension filter; Store profile has no such assertion, so no Apps. |
| `EdgeConnect` with explicit MQTT capability filter | No Apps: unsupported metadata fails closed even when the name matches. |
| `reset`, then `EdgeConnect` | Real session reset, then the App is retrieved again. |

Unmodified full-text search does not strip question wording: it normally requires
all query terms, so a question can miss even when a shorter name query matches.
Prices are outside the normalized Store projection. Comparisons/detail follow-ups
lack a complete Store-aware dialogue binding. Do not interpret returned candidates
or static help text as successful answers to these unsupported requests.

Verification: **440 unit tests and 100 guarded integration tests passed**, with
**92.46% shared branch coverage** in the unit run. Ruff, shell syntax and whitespace
checks passed. The 16 diagnostic turns and interactive commands were run against
the disposable resources above. Original demo/runtime fingerprints were unchanged.
One existing Starlette/httpx deprecation warning remains.

These observations identify future work, not algorithm adjustments in this slice.
A separately reviewed Store dialogue binding and available real pinned embeddings
would be needed before assessing natural-language/semantic usefulness; corpus rights,
backend credentials and public UI decisions remain gates in the
[integration baseline](integration-baseline.md). See the
[offline projection](store-v1-offline-recommendations.md) for retrieval guarantees.
