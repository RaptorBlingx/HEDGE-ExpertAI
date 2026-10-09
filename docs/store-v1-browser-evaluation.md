# Isolated Store chat evaluation

This is a local evaluation adapter, not an approved native Store UI or a production
endpoint. It reuses the standalone widget and existing Python dialogue/recommendation
pipeline. Store transport, scheduling, public indexing and gateway contracts remain
unchanged. No credentials or private authenticated responses are used.

## Start and access

```sh
cd /home/ubuntu/hedge
# Usable semantic evaluation: real pinned E5, explicitly labelled regex NLU
bash scripts/store-v1-playground.sh --browser --embeddings
```

Open **http://127.0.0.1:8091**. Keep the launcher running; Ctrl-C removes only its
uniquely named containers, networks and temporary data. Use `--port 8092` if 8091
is occupied by another evaluation. For a remote host, forward the chosen loopback
port using SSH; do not change the bind address or open a public firewall port:

```sh
ssh -N -L 8091:127.0.0.1:8091 ubuntu@<development-host>
```

For the lighter mode, omit `--embeddings`: the actual PostgreSQL lexical fallback
runs, with no fake vectors. For **experimental real Rasa diagnostics**, add `--rasa`.
That option starts a separate instance of the locally cached trained image, not the
demo instance. It is currently unsuitable as the default (see observed results).
`--help` prints launcher and CLI options without starting resources.

The first embedding build downloads the pinned public E5 snapshot
`614241f622f53c4eeff9890bdc4f31cfecc418b3` into a separate local developer image,
using the existing discovery image's CPU dependencies. Subsequent runs use build
cache and offline model loading. No demo model cache, volume or service is used.
Cached repository-pinned PostgreSQL/Qdrant/Valkey images are required. Per-run limits:
256 MiB each for PostgreSQL and Qdrant, 64 MiB Valkey, 512 MiB runner (1 GiB with
E5), optionally 768 MiB Rasa. CPU threads are bounded; optional model startup checks
host available memory. BuildKit may ignore Docker build memory flags: bootstrap
is a separate resource cost, and model mode should be run one session at a time.

Database, vector collection and sessions are disposable and isolated on an internal
network. Only the runner also joins a separate browser network and publishes a
loopback port. It has no Store transport configuration or tokens. Source is mounted
read-only; the server exposes only widget/evaluation static directories, not the
repository. Host/origin checks reject browser cross-origin writes and DNS rebinding.
This local boundary is not a production authentication design.

After an abnormal launcher kill, inspect `docker ps -a` / `docker network ls`.
Remove only that abandoned `hedge-store-cli-tmp.*` run's runner, optional Rasa,
sessions, vectors and database, then its matching network and `-ui` network.
Never prune broadly. Local `hedge-store-browser:local` / `hedge-store-models:local`
images are retained for reuse. Existing runtime resources remain independent.

## Evaluate real multi-turn behavior

Try in order:

1. `Show me EdgeConnect and Semantic Treehouse`
2. `Tell me more about the second app`
3. `hello`, then `Compare the first two apps`
4. `What does it cost?`, then `Tell me more about the first app`
5. Reload the page, then `Describe it`
6. `Does it support MQTT?`
7. `Find apps for sensor readings`, then `Find apps for semantic data models`
8. `reset`, then `Tell me about the second app`

Cards show actual ordering, native Store/App identity and retrieval channels; no
quality score, inferred category, latest version or fabricated navigation link.
Details/comparisons rehydrate current eligible PostgreSQL records using local IDs
bound to native identity. Cached result order supplies references, never facts.
Detail selection preserves the original list for subsequent comparisons. Small talk
and unsupported requests preserve search context; a new search replaces it even
when empty. Unknown/out-of-range or withdrawn references ask for a new search.
Prices, structured capabilities and unsupported metadata/filters cannot be confirmed.
Comparisons quote supplied fields without asserting superiority or suitability.

Conversation state/history survives page reload in the same tab for the existing
30-minute Valkey TTL; startup/restart discards it. Clear and `reset` erase context.
Restored cards are rechecked against PostgreSQL. Historical messages remain history.
Turns are serialized in this single local evaluation process, including streams.

SSE sends actual stage/result/explanation/complete events. Store text is buffered
until the dialogue turn finishes and delivered as validated source quotations,
not simulated LLM token generation. PostgreSQL/recommendation failure emits a
terminal problem without successful completion. Inter-service HTTP calls are
in-process bridges; the browser-to-runner HTTP/SSE calls are real. The production
service mesh, gateway authentication and native Angular integration are not tested.

## Evidence and limitations (2026-10-09)

[Fixture records](../tests/fixtures/store-v1/manual-apps.json) use the requested names
and invented IDs/publication dates. Useful descriptions are **authored diagnostic
examples**, explicitly labelled in each record. They are source evidence within
this fixture corpus, not verified claims about the real products. Providers, URLs,
versions and embedded metadata remain sparse; no Assets or private samples are joined.
README/HTML/embedded metadata stay outside recommendations; displayed strings are
untrusted and escaped. Inspect the page's source-record/status panel and SSE `nlu`
field to distinguish configured components from each turn's actual classifier.

Real E5 indexing/query encoding ran against isolated Qdrant. Lexical-only and
E5-plus-regex browser flows exercise search, ordinal details, source comparisons,
unsupported requests, reload history, reset/clear and escaping. These checks establish
wiring, not corpus quality, relevance thresholds or proposal KPIs. With two records,
dense retrieval can return weak nearest neighbours; returned Apps are candidates.

Real Rasa started and served requests, but classified `Show me EdgeConnect and
Semantic Treehouse` as `help` with confidence **1.0**, returning no Apps. That
observed model limitation was retained, not replaced with invented success or fixed
by changing ranking. NLU acceptance/training for Store language remains separate work.
The cached embedding dependencies also emit a tokenizer-regex warning when loading
the saved E5 model; compatibility review remains pending before quality acceptance.
Ollama is absent from the running stack and deliberately blocked in this runner:
Store narratives use deterministic source quotations, not generative reasoning.

Browser regression (Playwright 1.56.1, separate tooling; no application dependency):

```sh
npm install --prefix /tmp/hedge-store-browser-tools --no-audit --no-fund playwright@1.56.1
PLAYWRIGHT_BROWSERS_PATH=/tmp/hedge-store-browser-tools/browsers \
  /tmp/hedge-store-browser-tools/node_modules/.bin/playwright install chromium
NODE_PATH=/tmp/hedge-store-browser-tools/node_modules \
PLAYWRIGHT_BROWSERS_PATH=/tmp/hedge-store-browser-tools/browsers \
STORE_BROWSER_URL=http://127.0.0.1:8091 node tests/browser/store-v1-chat.cjs
```

Use the same explicitly disposable resource setup for PostgreSQL regression tests.
[Offline projection](store-v1-offline-recommendations.md) and the
[integration baseline](integration-baseline.md) retain public/live integration gates.

Retained local verification for this slice: **457 unit tests**, **103 guarded
PostgreSQL/Qdrant integration tests**, shared branch coverage **92.46%**; browser
multi-turn checks passed with lexical-only and real E5 retrieval. An actual disposable
PostgreSQL outage produced a terminal SSE problem and “Request failed”, with no cards
or successful completion. The 16 CLI diagnostics, Ruff, shell/JS syntax and documentation
links passed; six regenerated production OpenAPI files were byte-identical. The React
console test passed under CI-pinned Node 20.19.4 (host Node 18 could not initialize its
ESM test dependency). One existing Starlette/httpx deprecation warning remains.
Original container identities, mounts/start times and the frozen demo's clean pinned
revision were unchanged. No live Store ingestion, deployment or production migrations.
